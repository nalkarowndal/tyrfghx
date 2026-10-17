//! M3-3: Windows DEBUG-only, explicit, single-owner local generation process.
//! No shell plugin, frontend executable/path/argument selection, HTTP execution,
//! automatic downloads, or production release execution.
use serde::{Deserialize, Serialize};
use std::{
    io::Read,
    sync::mpsc,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, State};

const MAX_JOB_RUNTIME: Duration = Duration::from_secs(30 * 60);
const MAX_STDERR_TAIL: usize = 8192;

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
    pub elapsed_seconds: u64,
    pub time_limit_seconds: u64,
    pub result: Option<super::generation_result::VerifiedResult>,
}

struct RunningJob {
    snapshot: Arc<Mutex<JobSnapshot>>,
    process: Arc<Mutex<Child>>,
    cancelling: Arc<AtomicBool>,
    process_group: Arc<super::windows_process_job::ProcessJob>,
}

#[derive(Default)]
pub struct JobManager {
    next_id: AtomicU64,
    current: Mutex<Option<RunningJob>>,
    diagnostic_active: Arc<AtomicBool>,
}

pub(crate) struct DiagnosticPermit(Arc<AtomicBool>);
impl Drop for DiagnosticPermit {
    fn drop(&mut self) { self.0.store(false, Ordering::SeqCst); }
}

impl JobManager {
    /// A scoped single-flight diagnostic reservation: protects concurrent
    /// windows and prevents a CUDA check overlapping with live inference.
    pub(crate) fn reserve_diagnostic(&self) -> Result<DiagnosticPermit, String> {
        let guard = self.current.lock().map_err(|_| "Job manager unavailable")?;
        if let Some(job) = guard.as_ref() {
            let status = job.snapshot.lock().map_err(|_| "Job status unavailable")?;
            if status.phase == "running" || status.phase == "cancelling" {
                return Err("이미지 생성 중에는 CUDA 진단을 시작할 수 없습니다.".into());
            }
        }
        self.diagnostic_active.compare_exchange(false, true,
            Ordering::SeqCst, Ordering::SeqCst)
            .map_err(|_| "이미 CUDA 환경 진단이 진행 중입니다.".to_string())?;
        Ok(DiagnosticPermit(Arc::clone(&self.diagnostic_active)))
    }
}

impl Drop for JobManager {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.current.lock() {
            if let Some(job) = guard.take() {
                job.cancelling.store(true, Ordering::SeqCst);
                if job.process_group.terminate().is_err() {
                    if let Ok(mut child) = job.process.lock() {
                        let _ = child.kill();
                    }
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

/// Read a bounded tail; never join this thread in the worker, because
/// inherited stderr handles may remain open in child processes.
fn consume_tail(mut stream: impl Read, shared: Arc<Mutex<Vec<u8>>>) {
    let mut buf = [0_u8; 4096];
    loop {
        match stream.read(&mut buf) {
            Ok(0) | Err(_) => break,
            Ok(len) => {
                if let Ok(mut tail) = shared.lock() {
                    tail.extend_from_slice(&buf[..len]);
                    let extra = tail.len().saturating_sub(MAX_STDERR_TAIL);
                    if extra != 0 { tail.drain(..extra); }
                } else { break; }
            }
        }
    }
}

fn consume_bounded_stdout(mut pipe: impl Read) -> Result<Vec<u8>, String> {
    // Always drain to EOF to avoid filling OS pipes and deadlocking Python.
    // Store at most MAX_OUTPUT_JSON + 1 bytes so an oversized report is rejected.
    let limit = super::generation_result::MAX_OUTPUT_JSON + 1;
    let mut captured = Vec::new();
    let mut buf = [0u8; 4096];
    loop {
        let count = pipe.read(&mut buf)
            .map_err(|_| "생성 결과 출력 수집에 실패했습니다.".to_string())?;
        if count == 0 { break; }
        let keep = (limit - captured.len()).min(count);
        captured.extend_from_slice(&buf[..keep]);
    }
    Ok(captured)
}

fn is_over_limit(start: Instant, limit: Duration) -> bool {
    start.elapsed() >= limit
}

fn outcome_message(ok: bool, stderr: &str, code: Option<i32>, cancelled: bool, timed_out: bool) -> (String, String) {
    if timed_out {
        return ("timed_out".into(), "최대 실행 시간 30분을 초과해 종료되었습니다. 설정과 GPU 환경을 확인하세요.".into());
    }
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
pub fn local_generation_supported() -> bool {
    cfg!(all(windows, debug_assertions))
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
    if state.diagnostic_active.load(Ordering::SeqCst) {
        return Err("GPU 환경 검사 중에는 모델 생성을 시작할 수 없습니다.".into());
    }
    if let Some(job) = guard.as_ref() {
        let phase = job.snapshot.lock().map_err(|_| "Job state lock error")?.phase.clone();
        if phase == "running" || phase == "cancelling" {
            return Err("Another generation job is already running".into());
        }
    }

    let mut command = Command::new(python);
    command
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
               "--execute", "--metrics"])
        .current_dir(&repo)
        .env("HF_HUB_OFFLINE", "1")
        .env("HF_HUB_DISABLE_TELEMETRY", "1")
        .env("PYTHONNOUSERSITE", "1")
        .env_remove("PYTHONPATH")
        .env_remove("PYTHONHOME")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    super::windows_process_job::prepare_command(&mut command);
    let mut child = command.spawn()
        .map_err(|e| format!("Could not start suspended Python interpreter: {e}"))?;
    let group = match super::windows_process_job::ProcessJob::attach_and_resume(&mut child) {
        Ok(group) => Arc::new(group),
        Err(error) => {
            // Fail closed: NEVER allow an unmonitored Python process.
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }
    };
    // Consume stdout concurrently with stderr to avoid pipe-buffer deadlock;
    // cap memory before the subprocess can write more than the limit.
    let stdout = child.stdout.take().ok_or("Cannot capture inference metrics")?;
    let (result_sender, result_receiver) = mpsc::sync_channel(1);
    thread::spawn(move || {
        let response = consume_bounded_stdout(stdout);
        let _ = result_sender.send(response);
    });
    let stderr = child.stderr.take().ok_or("Cannot capture subprocess diagnostics")?;
    let stderr_tail = Arc::new(Mutex::new(Vec::new()));
    let reader_tail = Arc::clone(&stderr_tail);
    thread::spawn(move || consume_tail(stderr, reader_tail));
    let id = state.next_id.fetch_add(1, Ordering::SeqCst) + 1;
    let snapshot = Arc::new(Mutex::new(JobSnapshot {
        job_id: id,
        phase: "running".into(),
        message: "로컬 GPU 생성 중 (최대 30분, 단계별 진행률 미제공).".into(),
        elapsed_seconds: 0,
        time_limit_seconds: MAX_JOB_RUNTIME.as_secs(),
        result: None,
    }));
    let process = Arc::new(Mutex::new(child));
    let cancelling = Arc::new(AtomicBool::new(false));
    let worker_process = Arc::clone(&process);
    let worker_snapshot = Arc::clone(&snapshot);
    let worker_cancelled = Arc::clone(&cancelling);
    let worker_group = Arc::clone(&group);
    let output_root = repo.join("outputs");
    let expected_seed = request.seed;
    thread::spawn(move || {
        let started = Instant::now();
        let mut timed_out = false;
        let exit_status = loop {
            let result = match worker_process.lock() {
                Ok(mut child) => child.try_wait(),
                Err(_) => break None,
            };
            match result {
                Ok(Some(exit)) => break Some(exit),
                Err(_) => break None,
                Ok(None) => {
                    if is_over_limit(started, MAX_JOB_RUNTIME) && !timed_out {
                        timed_out = true;
                        if worker_group.terminate().is_err() {
                            // Best effort if Win32 Job Objects termination fails.
                            if let Ok(mut child) = worker_process.lock() {
                                let _ = child.kill();
                            }
                        }
                        if let Ok(mut status) = worker_snapshot.lock() {
                            status.phase = "cancelling".into();
                            status.message = "30분 제한에 도달하여 종료를 요청했습니다.".into();
                        }
                    }
                    if let Ok(mut status) = worker_snapshot.lock() {
                        status.elapsed_seconds = started.elapsed().as_secs();
                    }
                    thread::sleep(Duration::from_millis(150));
                }
            }
        };
        // Short grace period for stderr classification. Do not join the pipe
        // reader, which could block forever if a descendant holds the pipe.
        thread::sleep(Duration::from_millis(80));
        let stderr = stderr_tail.lock()
            .map(|bytes| String::from_utf8_lossy(&bytes).to_string())
            .unwrap_or_default();
        // Python may exit while its spawned workers are still running.
        // End the process group before announcing terminal completion.
        let group_cleanup = worker_group.terminate();
        let (mut phase, mut message) = outcome_message(
            exit_status.as_ref().is_some_and(|s| s.success()),
            &stderr,
            exit_status.as_ref().and_then(|s| s.code()),
            worker_cancelled.load(Ordering::SeqCst),
            timed_out,
        );
        if group_cleanup.is_err() && phase == "succeeded" {
            phase = "failed".into();
            message = "Python은 종료됐으나 하위 프로세스 정리를 확인하지 못했습니다.".into();
        }
        let mut verified = None;
        if phase == "succeeded" {
            let parsed = result_receiver.recv_timeout(Duration::from_secs(2))
                .map_err(|_| "생성 결과 수신 시간이 초과됐습니다.".to_string())
                .and_then(|response| response.map_err(|_| "생성 결과 읽기에 실패했습니다.".into()))
                .and_then(|bytes| super::generation_result::validate_report(
                    &bytes, &output_root, expected_seed
                ));
            match parsed {
                Ok(result) => {
                    verified = Some(result);
                    message = "Python 실행이 종료됐고 결과 PNG 시그니처·SHA-256 검증이 통과했습니다. 화질·CUDA 장치 동작 검증과는 별개입니다.".into();
                }
                Err(problem) => {
                    phase = "failed".into();
                    message = format!("생성 프로세스는 성공 종료했지만 결과 검증에 실패했습니다: {problem}");
                }
            }
        }
        if let Ok(mut status) = worker_snapshot.lock() {
            status.elapsed_seconds = started.elapsed().as_secs();
            status.phase = phase;
            status.message = message;
            status.result = verified;
        }
    });
    let reply = snapshot.lock().map_err(|_| "Job state lock error")?.clone();
    *guard = Some(RunningJob { snapshot, process, cancelling, process_group: group });
    Ok(reply)
}

#[tauri::command]
pub async fn generation_job_status(state: State<'_, JobManager>) -> Result<JobSnapshot, String> {
    let guard = state.current.lock().map_err(|_| "Job manager lock error")?;
    let Some(job) = guard.as_ref() else {
        return Ok(JobSnapshot {
            job_id: 0, phase: "idle".into(), message: "대기 중".into(),
            elapsed_seconds: 0, time_limit_seconds: MAX_JOB_RUNTIME.as_secs(),
            result: None,
        });
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
    job.cancelling.store(true, Ordering::SeqCst);
    if let Err(error) = job.process_group.terminate() {
        job.cancelling.store(false, Ordering::SeqCst);
        return Err(error);
    }
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
        assert_eq!(outcome_message(false, "CUDA out of memory", Some(1), false, false).0, "failed");
        assert!(outcome_message(false, "CUDA out of memory", Some(1), false, false).1.contains("VRAM"));
        assert_eq!(outcome_message(false, "", Some(1), true, false).0, "cancelled");
        assert_eq!(outcome_message(true, "", Some(0), false, false).0, "succeeded");
    }
    #[test] fn cannot_start_without_fixed_interpreter_and_config() {
        let dir = tempfile::tempdir().unwrap();
        assert!(validate_local_files(dir.path(), &dir.path().join("models"), &request()).is_err());
    }
    #[test] fn drain_stderr_has_bounded_memory() {
        let shared = Arc::new(Mutex::new(Vec::new()));
        consume_tail(std::io::Cursor::new(vec![b'X'; 50000]), Arc::clone(&shared));
        assert_eq!(shared.lock().unwrap().len(), MAX_STDERR_TAIL);
    }
    #[test] fn capped_stdout_reader_drains_all_data_and_marks_oversize() {
        let payload = vec![b'X'; super::generation_result::MAX_OUTPUT_JSON + 99_000];
        let mut reader = std::io::Cursor::new(&payload);
        let stored = consume_bounded_stdout(&mut reader).unwrap();
        assert_eq!(stored.len(), super::generation_result::MAX_OUTPUT_JSON + 1);
        assert_eq!(reader.position() as usize, payload.len());
    }

    #[test] fn runtime_limit_and_timeout_result() {
        let earlier = Instant::now() - Duration::from_secs(5);
        assert!(is_over_limit(earlier, Duration::from_secs(3)));
        assert!(!is_over_limit(earlier, Duration::from_secs(10)));
        let (phase, message) = outcome_message(false, "CUDA out of memory", None, false, true);
        assert_eq!(phase, "timed_out");
        assert!(message.contains("30분"));
    }

    #[test] fn diagnostic_reservation_is_single_flight_and_releases_on_drop() {
        let state = JobManager::default();
        let permit = state.reserve_diagnostic().unwrap();
        assert!(state.reserve_diagnostic().is_err());
        assert!(state.diagnostic_active.load(Ordering::SeqCst));
        drop(permit);
        assert!(!state.diagnostic_active.load(Ordering::SeqCst));
        assert!(state.reserve_diagnostic().is_ok());
    }

}
