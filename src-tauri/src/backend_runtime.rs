//! Fixed, authenticated read-only API child. No GPU or general-purpose HTTP IPC.
use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Read, Write},
    net::{Ipv4Addr, SocketAddr, TcpStream},
    path::Path,
    process::{Child, ChildStdin, Command, Stdio},
    sync::{mpsc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::Manager;
use crate::windows_process_job::{prepare_hidden_command, ProcessJob};

const START_TIMEOUT: Duration = Duration::from_secs(20);
const STOP_TIMEOUT: Duration = Duration::from_secs(4);
const IO_TIMEOUT: Duration = Duration::from_secs(2);

// Deliberately not Debug/Serialize: the token must not escape native memory.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Ready {
    protocol: u32,
    host: String,
    port: u16,
    token: String,
    pid: u32,
}

fn parse_ready(line: &[u8], pid: u32) -> Result<Ready, String> {
    let ready: Ready = serde_json::from_slice(line).map_err(|_| "backend_protocol_failed")?;
    if line.len() > 4096 || ready.protocol != 1 || ready.host != "127.0.0.1"
        || ready.port < 1024 || ready.pid != pid || ready.token.len() != 64
        || !ready.token.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("backend_protocol_failed".into());
    }
    Ok(ready)
}

fn request_status(ready: &Ready) -> Result<Value, String> {
    let address = SocketAddr::from((Ipv4Addr::LOCALHOST, ready.port));
    let mut stream = TcpStream::connect_timeout(&address, IO_TIMEOUT)
        .map_err(|_| "backend_unavailable")?;
    stream.set_read_timeout(Some(IO_TIMEOUT)).map_err(|_| "backend_unavailable")?;
    stream.set_write_timeout(Some(IO_TIMEOUT)).map_err(|_| "backend_unavailable")?;
    write!(stream, "GET /api/status HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n", ready.port, ready.token)
        .map_err(|_| "backend_unavailable")?;
    let mut bytes = Vec::new();
    stream.take(16_385).read_to_end(&mut bytes).map_err(|_| "backend_unavailable")?;
    if bytes.len() > 16_384 { return Err("backend_protocol_failed".into()); }
    let response = std::str::from_utf8(&bytes).map_err(|_| "backend_protocol_failed")?;
    let (header, body) = response.split_once("\r\n\r\n").ok_or("backend_protocol_failed")?;
    if !header.starts_with("HTTP/1.1 200 ") { return Err("backend_unavailable".into()); }
    let value: Value = serde_json::from_str(body).map_err(|_| "backend_protocol_failed")?;
    if value["app"] != "aiimage" || !value["engines"].is_array() {
        return Err("backend_protocol_failed".into());
    }
    Ok(value)
}

struct Session {
    child: Child,
    input: Option<ChildStdin>,
    job: ProcessJob,
    ready: Option<Ready>,
}

impl Session {
    fn stop(&mut self) -> Result<(), String> {
        self.input.take(); // EOF asks Uvicorn to stop accepting and drain requests.
        let until = Instant::now() + STOP_TIMEOUT;
        while Instant::now() < until {
            if self.child.try_wait().map_err(|_| "backend_cleanup_failed")?.is_some() {
                // Even an exited parent could have descendants. Check the entire job.
                if self.job.verify_drained(Duration::from_millis(100)).is_ok() { return Ok(()); }
                break;
            }
            thread::sleep(Duration::from_millis(25));
        }
        self.job.terminate().map_err(|_| "backend_cleanup_failed")?;
        self.job.verify_drained(STOP_TIMEOUT).map_err(|_| "backend_cleanup_failed")?;
        self.child.wait().map_err(|_| "backend_cleanup_failed")?;
        Ok(())
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        // OS kill-on-close remains the final safeguard if graceful cleanup fails.
        let _ = self.stop();
    }
}

#[derive(Default)]
pub(crate) struct BackendManager {
    session: Option<Session>,
    failed: bool,
}

#[derive(Default)]
pub struct BackendState(Mutex<BackendManager>);

impl BackendManager {
    fn stop(&mut self) -> Result<(), String> {
        if let Some(session) = self.session.as_mut() {
            // Retain ownership on failure. Never replace an unverified live group.
            session.stop()?;
        }
        self.session.take();
        Ok(())
    }

    fn start(&mut self, executable: &Path, root: &Path) -> Result<(), String> {
        if !cfg!(windows) { return Err("backend_windows_required".into()); }
        if !root.is_absolute() || !executable.is_absolute() || executable.is_symlink() || !executable.is_file() {
            return Err("backend_bundle_missing".into());
        }
        let mut command = Command::new(executable);
        command.current_dir(executable.parent().ok_or("backend_bundle_missing")?)
            .env_remove("PYTHONPATH").env_remove("PYTHONHOME")
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
        prepare_hidden_command(&mut command);
        let mut child = command.spawn().map_err(|_| "backend_start_failed")?;
        let job = match ProcessJob::attach_and_resume(&mut child) {
            Ok(job) => job,
            Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err("backend_job_failed".into());
            }
        };
        let mut input = child.stdin.take().ok_or("backend_start_failed")?;
        let output = child.stdout.take().ok_or("backend_start_failed")?;
        let pid = child.id();
        self.session = Some(Session { child, input: None, job, ready: None });
        let session = self.session.as_mut().ok_or("backend_start_failed")?;
        let bootstrap = json!({"protocol": 1, "model_root": root}).to_string() + "\n";
        if bootstrap.len() > 8192 { return Err("backend_path_too_long".into()); }
        let deadline = Instant::now() + START_TIMEOUT;
        let (input_send, input_receive) = mpsc::sync_channel(1);
        thread::spawn(move || {
            let result = input.write_all(bootstrap.as_bytes())
                .map(|_| input).map_err(|_| "backend_start_failed".to_owned());
            let _ = input_send.send(result);
        });
        let (send, receive) = mpsc::sync_channel(1);
        thread::spawn(move || {
            let mut line = Vec::new();
            let result = BufReader::new(output.take(4097)).read_until(b'\n', &mut line)
                .map_err(|_| "backend_protocol_failed".to_owned())
                .and_then(|_| parse_ready(&line, pid));
            let _ = send.send(result);
        });
        session.input = Some(input_receive.recv_timeout(deadline.saturating_duration_since(Instant::now()))
            .map_err(|_| "backend_start_timeout")??);
        session.ready = Some(receive.recv_timeout(deadline.saturating_duration_since(Instant::now()))
            .map_err(|_| "backend_start_timeout")??);
        Ok(())
    }

    fn status(&mut self, executable: &Path, root: &Path) -> Result<Value, String> {
        if self.failed { return Err("backend_retry_required".into()); }
        let result = (|| {
            if self.session.is_none() { self.start(executable, root)?; }
            let session = self.session.as_mut().ok_or("backend_unavailable")?;
            if session.child.try_wait().map_err(|_| "backend_unavailable")?.is_some() {
                return Err("backend_exited".into());
            }
            request_status(session.ready.as_ref().ok_or("backend_unavailable")?)
        })();
        if result.is_err() {
            self.failed = true;
            self.stop()?;
        }
        result
    }

    fn restart(&mut self, executable: &Path, root: &Path) -> Result<Value, String> {
        self.failed = true;
        self.stop()?;
        self.failed = false;
        self.status(executable, root)
    }
}

#[tauri::command]
pub fn bundled_backend_enabled() -> bool { cfg!(all(windows, feature = "bundled-backend")) }

fn bundled_executable(resource: &Path) -> Result<std::path::PathBuf, String> {
    let resource = resource.canonicalize().map_err(|_| "backend_bundle_missing")?;
    let folder = resource.join("backend");
    let exe = folder.join("aiimage-backend.exe");
    if folder.is_symlink() || exe.is_symlink() || !exe.is_file()
        || exe.canonicalize().map_err(|_| "backend_bundle_missing")? != exe
    { return Err("backend_bundle_missing".into()); }
    Ok(exe)
}

async fn operate(app: tauri::AppHandle, restart: bool) -> Result<Value, String> {
    if !bundled_backend_enabled() { return Err("backend_not_bundled".into()); }
    let executable = bundled_executable(&app.path().resource_dir().map_err(|_| "backend_bundle_missing")?)?;
    let root = crate::model_import::model_root(&app)?;
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<BackendState>();
        let mut manager = state.0.lock().map_err(|_| "backend_state_failed")?;
        if restart { manager.restart(&executable, &root) } else { manager.status(&executable, &root) }
    }).await.map_err(|_| "backend_state_failed".to_owned())?
}

#[tauri::command]
pub async fn backend_status(app: tauri::AppHandle) -> Result<Value, String> { operate(app, false).await }

#[tauri::command]
pub async fn restart_backend(app: tauri::AppHandle) -> Result<Value, String> { operate(app, true).await }

pub fn shutdown(app: &tauri::AppHandle) {
    let state = app.state::<BackendState>();
    if let Ok(mut manager) = state.0.lock() { let _ = manager.stop(); };
}

#[cfg(test)]
mod tests {
    use super::*;

    fn message() -> Value {
        json!({"protocol":1,"host":"127.0.0.1","port":12345,"token":"a".repeat(64),"pid":42})
    }

    #[test]
    fn rejects_remote_malformed_or_unowned_readiness() {
        assert!(parse_ready(message().to_string().as_bytes(), 42).is_ok());
        for (key, value) in [("protocol", json!(2)), ("host", json!("evil.example")), ("port", json!(80)),
            ("token", json!("secret\r\nInjected: header")), ("pid", json!(43)), ("extra", json!(true))] {
            let mut msg = message(); msg[key] = value;
            assert!(parse_ready(msg.to_string().as_bytes(), 42).is_err());
        }
        assert!(parse_ready(b"not json", 42).is_err());
        assert!(parse_ready(&vec![b' '; 4097], 42).is_err());
    }

    #[test]
    fn missing_bundle_latches_failure_until_explicit_retry() {
        let temp = tempfile::tempdir().unwrap();
        let exe = temp.path().join("missing.exe");
        let mut manager = BackendManager::default();
        assert!(manager.status(&exe, temp.path()).is_err());
        assert_eq!(manager.status(&exe, temp.path()).unwrap_err(), "backend_retry_required");
        assert!(manager.restart(&exe, temp.path()).is_err());
        assert!(manager.session.is_none());
        assert!(bundled_executable(temp.path()).is_err());
    }

    #[cfg(windows)]
    #[test]
    #[ignore = "requires the disposable frozen backend produced by Windows bundle QA"]
    fn frozen_backend_lifecycle() {
        let exe = std::path::PathBuf::from(std::env::var_os("AIIMAGE_TEST_BACKEND").expect("QA executable required"));
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("한글 models");
        std::fs::create_dir(&root).unwrap();
        let sentinel = root.join("keep.txt");
        std::fs::write(&sentinel, b"user data").unwrap();
        let mut manager = BackendManager::default();
        assert_eq!(manager.status(&exe, &root).unwrap()["app"], "aiimage");
        let pid = manager.session.as_ref().unwrap().child.id();
        let token = manager.session.as_ref().unwrap().ready.as_ref().unwrap().token.clone();
        manager.status(&exe, &root).unwrap();
        assert_eq!(manager.session.as_ref().unwrap().child.id(), pid);
        let mut duplicate = BackendManager::default();
        assert!(duplicate.status(&exe, &root).is_err());
        assert!(duplicate.session.is_none());
        manager.session.as_mut().unwrap().child.kill().unwrap();
        manager.session.as_mut().unwrap().child.wait().unwrap();
        assert!(manager.status(&exe, &root).is_err());
        assert_eq!(manager.status(&exe, &root).unwrap_err(), "backend_retry_required");
        manager.restart(&exe, &root).unwrap();
        assert_ne!(manager.session.as_ref().unwrap().ready.as_ref().unwrap().token, token);
        manager.stop().unwrap();
        assert!(manager.session.is_none());
        duplicate.restart(&exe, &root).unwrap();
        drop(duplicate);
        assert_eq!(std::fs::read(&sentinel).unwrap(), b"user data");
        assert_eq!(std::fs::read_dir(&root).unwrap().count(), 1);
    }

    #[cfg(windows)]
    #[test]
    #[ignore = "requires the disposable Rust process fixture built by Windows QA"]
    fn stalled_bootstrap_is_bounded_and_owned_process_is_reaped() {
        let exe = std::path::PathBuf::from(std::env::var_os("AIIMAGE_TEST_STALLED_BACKEND").expect("QA fixture required"));
        let temp = tempfile::tempdir().unwrap();
        // Larger than the anonymous Windows pipe buffer; child deliberately never reads it.
        // This path is never opened or created.
        let root = temp.path().join("a".repeat(6000));
        let mut manager = BackendManager::default();
        let started = Instant::now();
        assert_eq!(manager.status(&exe, &root).unwrap_err(), "backend_start_timeout");
        assert!(started.elapsed() < START_TIMEOUT + STOP_TIMEOUT * 3);
        assert!(manager.session.is_none());
        assert!(manager.failed);
    }
}
