//! M3-7: restricted, owner-triggered GPU environment diagnostics for Tauri.
//! Runs only the fixed repository-local Python inspection script in Windows
//! development builds. No frontend paths, shell execution, network, model
//! weights, actual diffusion run, or inference work submitted by this command.

use serde::{Deserialize, Serialize};
use std::{
    io::Read,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{mpsc, Arc, atomic::{AtomicBool, Ordering}},
    thread,
    time::{Duration, Instant},
};
use tauri::State;

const TIMEOUT: Duration = Duration::from_secs(25);
const MAX_JSON_BYTES: usize = 16_384;

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GpuDetails {
    index: u32,
    name: String,
    compute_capability: String,
    total_vram_bytes: u64,
    free_vram_bytes_at_check: u64,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TrialSettings {
    width: u32,
    height: u32,
    steps: u32,
    images: u32,
    cpu_offload: bool,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GpuDiagnosticReport {
    schema_version: u32,
    status: String,
    os: String,
    torch_version: Option<String>,
    torch_cuda_build: Option<String>,
    gpu: Option<GpuDetails>,
    warnings: Vec<String>,
    trial_settings: TrialSettings,
}

fn parse_report(content: &[u8]) -> Result<GpuDiagnosticReport, String> {
    if content.is_empty() || content.len() > MAX_JSON_BYTES {
        return Err("GPU diagnostic response is empty or too large".into());
    }
    let report: GpuDiagnosticReport = serde_json::from_slice(content)
        .map_err(|_| "GPU diagnostic response has an invalid schema")?;
    if report.schema_version != 1 ||
        !matches!(report.status.as_str(),
            "ready_for_trial" | "torch_missing" | "torch_import_error" |
            "cpu_only_torch" | "unsupported_backend" | "cuda_unavailable" |
            "cuda_probe_error" | "unavailable")
        || report.os.len() > 40
        || report.torch_version.as_ref().is_some_and(|s| s.len() > 96)
        || report.torch_cuda_build.as_ref().is_some_and(|s| s.len() > 64)
        || report.warnings.len() > 8
        || report.warnings.iter().any(|s| s.len() > 400)
        || report.trial_settings.width != 512
        || report.trial_settings.height != 512
        || report.trial_settings.steps != 15
        || report.trial_settings.images != 1
        || !report.trial_settings.cpu_offload
    {
        return Err("GPU diagnostic response failed validity checks".into());
    }
    if let Some(gpu) = &report.gpu {
        if report.status != "ready_for_trial" || gpu.name.is_empty() ||
            gpu.name.len() > 120 || gpu.compute_capability.len() > 10 ||
            gpu.index > 16 || gpu.total_vram_bytes == 0 ||
            gpu.total_vram_bytes > 256 * 1024 * 1024 * 1024_u64 ||
            gpu.free_vram_bytes_at_check > gpu.total_vram_bytes
        {
            return Err("GPU diagnostic response has invalid device values".into());
        }
    } else if report.status == "ready_for_trial" {
        return Err("GPU diagnostic reported CUDA readiness without device details".into());
    }
    Ok(report)
}

fn trusted_python(repo: &Path) -> Result<PathBuf, String> {
    let venv = repo.join(".venv");
    let scripts = venv.join("Scripts");
    let python = scripts.join("python.exe");
    let backend = repo.join("backend");
    let tool = backend.join("gpu_diagnostics.py");
    if repo.is_symlink() || venv.is_symlink() || scripts.is_symlink() ||
        python.is_symlink() || !python.is_file() ||
        backend.is_symlink() || tool.is_symlink() || !tool.is_file()
    {
        return Err("GPU 검사에 필요한 로컬 .venv 또는 진단 스크립트를 찾지 못했습니다.".into());
    }
    Ok(python)
}

/// Run the exact same bounded, OS-supervised local CUDA probe used by
/// the diagnostics UI. The generation command evaluates memory thresholds
/// from the resulting device reading without trusting browser fields.
pub(crate) fn read_local_vram(
    repo: PathBuf, cleanup_fault: Arc<AtomicBool>
) -> Result<(u64, u64), String> {
    let report = run_probe(repo, cleanup_fault)?;
    if report.status != "ready_for_trial" {
        return Err(format!(
            "CUDA 환경 점검에 실패하여 생성을 차단했습니다 ({}). GPU 진단을 확인하세요.",
            report.status
        ));
    }
    let gpu = report.gpu.ok_or("GPU 장치 세부 정보가 없습니다.")?;
    Ok((gpu.total_vram_bytes, gpu.free_vram_bytes_at_check))
}

/// Every exit path for an attached diagnostic must verify complete process
/// cleanup. A missing signal is NOT equivalent to a successful Job drain.
/// Fail-closed, monotonic state: a later success must never clear a
/// previously observed unverified diagnostic process group.
fn latch_cleanup_result(fault: &AtomicBool, outcome: Result<(), String>) -> Result<(), String> {
    if outcome.is_err() {
        fault.store(true, Ordering::SeqCst);
        return Err("GPU 진단 종료 후 Windows 하위 프로세스 정리를 검증하지 못했습니다. 앱을 다시 시작하기 전까지 GPU 작업을 차단합니다.".into());
    }
    Ok(())
}

fn terminate_and_latch(
    job: &super::windows_process_job::ProcessJob,
    fault: &AtomicBool,
) -> Result<(), String> {
    let outcome = job.terminate().and_then(|_| job.verify_drained(Duration::from_secs(2)));
    latch_cleanup_result(fault, outcome)
}

fn run_probe(repo: PathBuf, cleanup_fault: Arc<AtomicBool>) -> Result<GpuDiagnosticReport, String> {
    let python = trusted_python(&repo)?;
    let mut cmd = Command::new(python);
    cmd.arg("-s")
        .arg("-B")
        .arg(repo.join("backend").join("gpu_diagnostics.py"))
        .current_dir(&repo)
        .env("HF_HUB_OFFLINE", "1")
        .env("HF_HUB_DISABLE_TELEMETRY", "1")
        .env("PYTHONNOUSERSITE", "1")
        .env_remove("PYTHONPATH")
        .env_remove("PYTHONHOME")
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .stdout(Stdio::piped());

    // Attach before starting Python user-space execution, and always fail
    // closed if the OS cannot create/assign the process group.
    super::windows_process_job::prepare_command(&mut cmd);
    let mut child: Child = cmd.spawn()
        .map_err(|_| "GPU 진단 Python 프로세스를 실행할 수 없습니다.".to_string())?;
    let job = match super::windows_process_job::ProcessJob::attach_and_resume(&mut child) {
        Ok(job) => job,
        Err(_) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err("Windows 프로세스 그룹 설정이 실패했습니다.".into());
        }
    };

    let pipe = match child.stdout.take() {
        Some(p) => p,
        None => {
            let _ = terminate_and_latch(&job, &cleanup_fault);
            let _ = child.wait();
            return Err("GPU 진단 결과를 읽을 수 없습니다.".into());
        }
    };
    let (sender, receiver) = mpsc::sync_channel(1);
    thread::spawn(move || {
        let mut buf = Vec::new();
        let result = pipe.take((MAX_JSON_BYTES + 1) as u64).read_to_end(&mut buf);
        let _ = sender.send(result.map(|_| buf));
    });

    let started = Instant::now();
    let exit_status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => {
                if started.elapsed() >= TIMEOUT {
                    let cleanup = terminate_and_latch(&job, &cleanup_fault);
                    let _ = child.kill();
                    let _ = child.wait();
                    cleanup?;
                    return Err("GPU 환경 진단이 25초 시간 제한을 초과했습니다.".into());
                }
                thread::sleep(Duration::from_millis(100));
            }
            Err(_) => {
                let cleanup = terminate_and_latch(&job, &cleanup_fault);
                let _ = child.kill();
                let _ = child.wait();
                cleanup?;
                return Err("GPU 진단 프로세스 상태를 확인하지 못했습니다.".into());
            }
        }
    };
    // Job group termination acknowledgement alone is insufficient:
    // verify that no active child or grandchild process remains.
    terminate_and_latch(&job, &cleanup_fault)?;
    if !exit_status.success() {
        return Err("GPU 진단 프로세스가 실패했습니다. 로컬 PyTorch 설치를 확인하세요.".into());
    }
    let bytes = receiver.recv_timeout(Duration::from_secs(2))
        .map_err(|_| "GPU 진단 출력 수집이 제한 시간을 초과했습니다.".to_string())?
        .map_err(|_| "GPU 진단 출력 읽기 실패".to_string())?;
    parse_report(&bytes)
}

#[tauri::command]
pub async fn inspect_local_gpu(
    state: State<'_, super::generation_jobs::JobManager>,
) -> Result<GpuDiagnosticReport, String> {
    if !cfg!(all(windows, debug_assertions)) {
        return Err("GPU 환경 검사는 Windows Tauri 개발판에서만 지원합니다.".into());
    }
    let permit = state.reserve_diagnostic()?;
    let cleanup_fault = state.cleanup_fault_flag();
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    tauri::async_runtime::spawn_blocking(move || {
        // Always release the reservation, even on error or panic.
        let _permit = permit;
        run_probe(repo, cleanup_fault)
    })
        .await.map_err(|_| "GPU 진단 백그라운드 작업이 종료됐습니다.".to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diagnostic_cleanup_failure_is_a_monotonic_safety_latch() {
        let fault = AtomicBool::new(false);
        assert!(latch_cleanup_result(&fault, Ok(())).is_ok());
        assert!(!fault.load(Ordering::SeqCst));
        let error = latch_cleanup_result(&fault, Err("Synthetic secret path".into())).unwrap_err();
        assert!(error.contains("앱을 다시 시작"));
        assert!(!error.contains("secret"));
        assert!(fault.load(Ordering::SeqCst));
        assert!(latch_cleanup_result(&fault, Ok(())).is_ok());
        assert!(fault.load(Ordering::SeqCst));
    }

    const OK_JSON: &str = r#"{
        "schema_version":1, "status":"ready_for_trial", "os":"Windows",
        "torch_version":"2.9", "torch_cuda_build":"12.8",
        "gpu":{"index":0,"name":"Fixture RTX 2060 SUPER",
               "compute_capability":"7.5",
               "total_vram_bytes":8589934592,"free_vram_bytes_at_check":6442450944},
        "warnings":["GPU readiness does not prove model inference"],
        "trial_settings":{"width":512,"height":512,"steps":15,"images":1,"cpu_offload":true}
    }"#;

    #[test]
    fn parses_gpu_ready_schema_without_treating_as_inference_success() {
        let r = parse_report(OK_JSON.as_bytes()).unwrap();
        assert_eq!(r.status, "ready_for_trial");
        assert_eq!(r.gpu.unwrap().name, "Fixture RTX 2060 SUPER");
    }

    #[test]
    fn rejects_oversized_and_unknown_fields() {
        assert!(parse_report(&vec![b'x'; MAX_JSON_BYTES+1]).is_err());
        let injected = OK_JSON.replace(r#""schema_version":1"#, r#""schema_version":1,"raw_path":"secret""#);
        assert!(parse_report(injected.as_bytes()).is_err());
    }

    #[test]
    fn rejects_false_cuda_ready_without_gpu_and_invalid_memory() {
        let missing = OK_JSON.replace(r#""gpu":{"index":0,"name":"Fixture RTX 2060 SUPER",
               "compute_capability":"7.5",
               "total_vram_bytes":8589934592,"free_vram_bytes_at_check":6442450944}"#, r#""gpu":null"#);
        assert!(parse_report(missing.as_bytes()).is_err());
        let invalid = OK_JSON.replace("6442450944", "9999999999");
        assert!(parse_report(invalid.as_bytes()).is_err());
    }

    #[test]
    fn cannot_execute_without_fixed_python_environment() {
        let tmp = tempfile::tempdir().unwrap();
        assert!(trusted_python(tmp.path()).is_err());
        assert!(run_probe(tmp.path().to_path_buf(), Arc::new(AtomicBool::new(false))).is_err());
    }
}
