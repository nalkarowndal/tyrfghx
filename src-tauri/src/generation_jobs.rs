//! M3-3: Windows DEBUG-only, explicit, single-owner local generation process.
//! No shell plugin, frontend executable/path/argument selection, HTTP execution,
//! automatic downloads, or production release execution.
use serde::{Deserialize, Serialize};
use std::{
    io::Read,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    thread,
    time::Duration,
};
use tauri::{AppHandle, State};

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct GenerateRequest {
    checkpoint_id: String,
    prompt: String,
    negative_prompt: String,
    width: u32,
    height: u32,
    steps: u32,
    guidance: f64,
    seed: u64,
    confirmed: bool,
}

#[derive(Clone, Serialize)]
pub struct JobSnapshot {
    pub job_id: u64,
    pub phase: String,
    pub message: String,
}

struct RunningJob {
    snapshot: Arc<Mutex<JobSnapshot>>,
    process: Arc<Mutex<Child>>,
    cancelling: Arc<AtomicBool>,
}

#[derive(Default)]
pub struct JobManager {
    next_id: AtomicU64,
    current: Mutex<Option<RunningJob>>,
}

impl Drop for JobManager {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.current.lock() {
            if let Some(job) = guard.take() {
                job.cancelling.store(true, Ordering::SeqCst);
                if let Ok(mut child) = job.process.lock() {
                    let _ = child.kill();
                }
            }
        }
    }
}

fn validate_request(r: &GenerateRequest) -> Result<(), String> {
    let mut parts = r.checkpoint_id.split('/');
    let group = parts.next().unwrap_or("");
    let file = parts.next().unwrap_or("");
    if group != "checkpoints" || parts.next().is_some()
        || file.is_empty() || file.contains('\\') || file.contains(':')
        || !file.to_ascii_lowercase().ends_with(".safetensors")
        || file == "." || file == ".."
    {
        return Err("Invalid checkpoint identifier".into());
    }
    if !r.confirmed {
        return Err("GPU generation requires explicit confirmation".into());
    }
    if r.prompt.trim().is_empty() || r.prompt.chars().count() > 2000
        || r.negative_prompt.chars().count() > 2000 {
        return Err("Prompt length is invalid".into());
    }
    if [r.width, r.height].iter().any(|n| *n < 512 || *n > 1024 || *n % 64 != 0)
        || r.steps < 1 || r.steps > 40
        || !r.guidance.is_finite() || !(1.0..=12.0).contains(&r.guidance)
        || r.seed > u32::MAX as u64 {
        return Err("Generation parameters are out of range".into());
    }
    Ok(())
}

fn validate_local_files(repo: &Path, model_root: &Path, r: &GenerateRequest) -> Result<PathBuf, String> {
    let checkpoint = model_root.join(&r.checkpoint_id);
    let config_dir = model_root.join("configs").join("sdxl-base-1.0");
    let config_file = config_dir.join("model_index.json");
    let python = repo.join(".venv").join("Scripts").join("python.exe");
    let script = repo.join("backend").join("generate_sdxl.py");

    if model_root.is_symlink() || model_root.join("checkpoints").is_symlink()
        || checkpoint.is_symlink() || !checkpoint.is_file() {
        return Err("Checkpoint missing or unsafe; import it in Model Management".into());
    }
    if model_root.join("configs").is_symlink() || config_dir.is_symlink()
        || config_file.is_symlink() || !config_file.is_file() {
        return Err("Local SDXL configuration is missing or unsafe".into());
    }
    if repo.join(".venv").is_symlink() || repo.join(".venv/Scripts").is_symlink() || repo.join("backend").is_symlink() || python.is_symlink() || !python.is_file()
        || script.is_symlink() || !script.is_file() {
        return Err("Local .venv/Scripts/python.exe or backend CLI missing; set up Python 3.12 first".into());
    }
    // This is only a family hint, not proof of model load compatibility.
    let models = super::model_catalog::scan_native_models(model_root)?;
    let eligible = models.iter().any(|model|
        model.id == r.checkpoint_id && model.category == "checkpoint"
            && model.validation == "metadata_only"
            && model.family.as_deref() == Some("sdxl")
    );
    if !eligible { return Err("No valid SDXL-family checkpoint metadata found".into()); }
    Ok(python)
}

/// Bound captured subprocess stderr memory. Drain the pipe to prevent deadlocks.
fn consume_tail(mut stream: impl Read) -> String {
    let mut tail = Vec::new();
    let mut block = [0u8; 4096];
    loop {
        match stream.read(&mut block) {
            Ok(0) | Err(_) => break,
            Ok(count) => {
                tail.extend_from_slice(&block[..count]);
                if tail.len() > 8192 {
                    tail.drain(..tail.len() - 8192);
                }
            }
        }
    }
    String::from_utf8_lossy(&tail).to_string()
}

fn outcome_message(ok: bool, stderr: &str, code: Option<i32>, cancelled: bool) -> (String, String) {
    if cancelled { return ("cancelled".into(), "사용자가 생성을 취소했습니다.".into()); }
    if ok {
        return ("succeeded".into(), "CLI 프로세스가 성공 종료했습니다. 결과 갤러리를 새로고침하세요.".into());
    }
    let text = stderr.to_ascii_lowercase();
    let reason = if text.contains("outofmemoryerror") || text.contains("cuda out of memory") {
        "GPU VRAM 부족: 512×512 해상도와 작은 스텝으로 다시 확인하세요."
    } else if text.contains("modulenotfounderror") || text.contains("no module named") {
        "Python 추론 패키지가 없습니다. .venv에 필요한 패키지를 설치하세요."
    } else if text.contains("cuda") {
        "CUDA 드라이버, PyTorch GPU 지원 및 설정을 확인하세요."
    } else {
        "모델·설정 파일 호환성이나 Python 실행 환경을 확인하세요."
    };
    ("failed".into(), format!("CLI 종료 코드 {:?}. {reason}", code))
}

#[tauri::command]
pub async fn start_local_generation(
    app: AppHandle,
    state: State<'_, JobManager>,
    request: GenerateRequest,
) -> Result<JobSnapshot, String> {
    if !cfg!(all(windows, debug_assertions)) {
        return Err("GPU job launch is disabled outside Windows Tauri development builds".into());
    }
    validate_request(&request)?;
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let models = super::model_import::model_root(&app)?;
    let python = validate_local_files(&repo, &models, &request)?;

    let mut guard = state.current.lock().map_err(|_| "Job manager lock error")?;
    if let Some(job) = guard.as_ref() {
        let phase = job.snapshot.lock().map_err(|_| "Job state lock error")?.phase.clone();
        if phase == "running" || phase == "cancelling" {
            return Err("Another generation job is already running".into());
        }
    }

    let mut child = Command::new(python)
        .arg("-s")
        .arg(repo.join("backend").join("generate_sdxl.py"))
        .args(["--checkpoint", &request.checkpoint_id,
               "--prompt", &request.prompt,
               "--negative-prompt", &request.negative_prompt,
               "--width", &request.width.to_string(),
               "--height", &request.height.to_string(),
               "--steps", &request.steps.to_string(),
               "--guidance", &request.guidance.to_string(),
               "--seed", &request.seed.to_string(),
               "--execute"])
        .current_dir(&repo)
        .env("HF_HUB_OFFLINE", "1")
        .env("HF_HUB_DISABLE_TELEMETRY", "1")
        .env("PYTHONNOUSERSITE", "1")
        .env_remove("PYTHONPATH")
        .env_remove("PYTHONHOME")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Could not start the fixed Python interpreter: {e}"))?;
    let stderr = child.stderr.take().ok_or("Cannot capture subprocess diagnostics")?;
    let reader = thread::spawn(move || consume_tail(stderr));
    let id = state.next_id.fetch_add(1, Ordering::SeqCst) + 1;
    let snapshot = Arc::new(Mutex::new(JobSnapshot {
        job_id: id,
        phase: "running".into(),
        message: "로컬 GPU 생성 프로세스 실행 중 (단계별 진행률은 아직 제공되지 않습니다).".into(),
    }));
    let process = Arc::new(Mutex::new(child));
    let cancelling = Arc::new(AtomicBool::new(false));
    let worker_process = Arc::clone(&process);
    let worker_snapshot = Arc::clone(&snapshot);
    let worker_cancelled = Arc::clone(&cancelling);
    thread::spawn(move || {
        let exit_status = loop {
            let result = match worker_process.lock() {
                Ok(mut child) => child.try_wait(),
                Err(_) => break None,
            };
            match result {
                Ok(Some(exit)) => break Some(exit),
                Err(_) => break None,
                Ok(None) => thread::sleep(Duration::from_millis(150)),
            }
        };
        let stderr = reader.join().unwrap_or_default();
        let (phase, message) = outcome_message(
            exit_status.as_ref().is_some_and(|s| s.success()),
            &stderr,
            exit_status.as_ref().and_then(|s| s.code()),
            worker_cancelled.load(Ordering::SeqCst),
        );
        if let Ok(mut status) = worker_snapshot.lock() {
            status.phase = phase;
            status.message = message;
        }
    });
    let reply = snapshot.lock().map_err(|_| "Job state lock error")?.clone();
    *guard = Some(RunningJob { snapshot, process, cancelling });
    Ok(reply)
}

#[tauri::command]
pub async fn generation_job_status(state: State<'_, JobManager>) -> Result<JobSnapshot, String> {
    let guard = state.current.lock().map_err(|_| "Job manager lock error")?;
    let Some(job) = guard.as_ref() else {
        return Ok(JobSnapshot { job_id: 0, phase: "idle".into(), message: "대기 중".into() });
    };
    job.snapshot.lock().map(|s| s.clone()).map_err(|_| "Job state lock error".into())
}

#[tauri::command]
pub async fn cancel_local_generation(
    state: State<'_, JobManager>, job_id: u64
) -> Result<JobSnapshot, String> {
    let guard = state.current.lock().map_err(|_| "Job manager lock error")?;
    let job = guard.as_ref().ok_or("No generation to cancel")?;
    let mut status = job.snapshot.lock().map_err(|_| "Job state lock error")?;
    if status.job_id != job_id || status.phase != "running" {
        return Err("This job is not running or its ID is out of date".into());
    }
    job.process.lock().map_err(|_| "Process lock error")?
        .kill().map_err(|e| format!("Could not cancel the process: {e}"))?;
    job.cancelling.store(true, Ordering::SeqCst);
    status.phase = "cancelling".into();
    status.message = "종료 신호를 보냈습니다. 실제 프로세스 종료 확인 중입니다.".into();
    Ok(status.clone())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request() -> GenerateRequest {
        GenerateRequest { checkpoint_id:"checkpoints/a.safetensors".into(),
            prompt:"a watercolor bird".into(),negative_prompt:"".into(),
            width:768,height:768,steps:20,guidance:7.0,seed:42,confirmed:true }
    }
    #[test] fn validates_supported_inputs_and_explicit_confirmation() {
        assert!(validate_request(&request()).is_ok());
        let mut bad = request();bad.confirmed=false;
        assert!(validate_request(&bad).is_err());
        let mut bad = request();bad.checkpoint_id="checkpoints/../../evil.safetensors".into();
        assert!(validate_request(&bad).is_err());
        let mut bad = request();bad.width=513;
        assert!(validate_request(&bad).is_err());
        let mut bad = request();bad.guidance=f64::NAN;
        assert!(validate_request(&bad).is_err());
    }
    #[test] fn distinguishes_oom_from_other_errors() {
        assert_eq!(outcome_message(false, "CUDA out of memory", Some(1), false).0, "failed");
        assert!(outcome_message(false, "CUDA out of memory", Some(1), false).1.contains("VRAM"));
        assert_eq!(outcome_message(false, "", Some(1), true).0, "cancelled");
        assert_eq!(outcome_message(true, "", Some(0), false).0, "succeeded");
    }
    #[test] fn cannot_start_without_fixed_interpreter_and_config() {
        let dir = tempfile::tempdir().unwrap();
        assert!(validate_local_files(dir.path(), &dir.path().join("models"), &request()).is_err());
    }
    #[test] fn drain_stderr_has_bounded_memory() {
        assert!(consume_tail(std::io::Cursor::new(vec![b'X';50000])).len()<=8192);
    }
}
