//! M4-1c TEST-ONLY Windows native owned-pipe integration.
//! No Tauri command, production sidecar, model, GPU or package installation.
//! CI uses a deterministic synthetic key; production must use OS-generated
//! ephemeral secrets, binary provenance and reviewed worker bootstrapping.
#![cfg(all(test, windows))]

use crate::windows_process_job::{prepare_hidden_command, ProcessJob};
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    io::{BufRead, BufReader, Read, Write},
    path::PathBuf,
    process::{Command, Stdio},
    sync::mpsc,
    thread,
    time::Duration,
};

const MAX_FRAME: usize = 4096;
const WAIT: Duration = Duration::from_secs(3);
const DOMAIN: &[u8] = b"aiimage-worker-parent-proof-v1\x00";
const REQUEST_ID: &str = "native_qa_001";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ParentProof {
    protocol_version: u32,
    operation: String,
    request_id: String,
    proof: String,
}

fn to_hex(bytes: &[u8]) -> String {
    use std::fmt::Write as _;
    let mut result = String::with_capacity(bytes.len() * 2);
    for byte in bytes { write!(&mut result, "{byte:02x}").expect("in-memory formatting"); }
    result
}

fn nibble(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        _ => None,
    }
}

fn parse_digest(value: &str) -> Option<[u8; 32]> {
    if value.len() != 64 { return None; }
    let mut result = [0u8; 32];
    for (i, pair) in value.as_bytes().chunks_exact(2).enumerate() {
        result[i] = (nibble(pair[0])? << 4) | nibble(pair[1])?;
    }
    Some(result)
}

// RFC 2104 HMAC-SHA256 using the EXISTING sha2 dependency (no Cargo.lock change).
// This cryptographic implementation is for isolated test-fixture comparison only.
fn hmac_test(key: &[u8; 32], message: &[u8]) -> [u8; 32] {
    let mut inner_pad = [0x36u8; 64];
    let mut outer_pad = [0x5cu8; 64];
    for i in 0..32 {
        inner_pad[i] ^= key[i];
        outer_pad[i] ^= key[i];
    }
    let mut inner = Sha256::new();
    inner.update(inner_pad);
    inner.update(message);
    let inner_hash = inner.finalize();
    let mut outer = Sha256::new();
    outer.update(outer_pad);
    outer.update(inner_hash);
    let digest = outer.finalize();
    let mut out = [0u8; 32];
    out.copy_from_slice(&digest);
    out
}

fn verify_proof(frame: &[u8], key: &[u8; 32], challenge: &[u8; 32]) -> Result<(), &'static str> {
    if frame.is_empty() || frame.len() > MAX_FRAME { return Err("invalid_frame"); }
    let packet: ParentProof = serde_json::from_slice(frame).map_err(|_| "invalid_proof_shape")?;
    if packet.protocol_version != 1 || packet.operation != "parent_proof" || packet.request_id != REQUEST_ID {
        return Err("invalid_proof_shape");
    }
    let got = parse_digest(&packet.proof).ok_or("invalid_proof_shape")?;
    let mut body = Vec::with_capacity(DOMAIN.len() + 32 + REQUEST_ID.len());
    body.extend_from_slice(DOMAIN);
    body.extend_from_slice(challenge);
    body.extend_from_slice(REQUEST_ID.as_bytes());
    let expected = hmac_test(key, &body);
    let mismatch = expected.iter().zip(got.iter()).fold(0u8, |acc, (a, b)| acc | (a ^ b));
    if mismatch != 0 { return Err("invalid_proof"); }
    Ok(())
}

fn take_frame<R: BufRead>(reader: &mut R) -> Result<Vec<u8>, &'static str> {
    let mut frame = Vec::new();
    let n = (&mut *reader)
        .take((MAX_FRAME + 1) as u64)
        .read_until(b'\n', &mut frame)
        .map_err(|_| "worker_io")?;
    if n == 0 { return Err("worker_eof"); }
    if n > MAX_FRAME || frame.last() != Some(&b'\n') { return Err("frame_limit"); }
    frame.pop();
    Ok(frame)
}

fn execute_fixture(mode: &'static str) -> Result<(), &'static str> {
    // Checked-in fixed path is only used under #[cfg(all(test, windows))].
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../backend/inference_worker_stdio_fixture.py")
        .canonicalize().map_err(|_| "fixture_missing")?;
    let mut command = Command::new("python");
    command.args(["-I", "-S"])
        .arg(&fixture)
        .arg(mode)
        .current_dir(fixture.parent().ok_or("fixture_missing")?)
        .env_remove("PYTHONPATH")
        .env_remove("PYTHONHOME")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());

    // Existing native Win32 manager creates the child SUSPENDED, attaches
    // it to the kill-on-close Job Object and ONLY THEN resumes execution.
    prepare_hidden_command(&mut command);
    let mut child = command.spawn().map_err(|_| "worker_spawn")?;
    let job = match ProcessJob::attach_and_resume(&mut child) {
        Ok(job) => job,
        Err(_) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err("worker_job");
        }
    };
    let mut stdin = child.stdin.take().ok_or("worker_io")?;
    let stdout = child.stdout.take().ok_or("worker_io")?;
    let (send, receive) = mpsc::sync_channel::<Result<Vec<u8>, &'static str>>(2);
    thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        for _ in 0..2 {
            let output = take_frame(&mut reader);
            let valid = output.is_ok();
            if send.send(output).is_err() || !valid { break; }
        }
    });

    // Synthetic, constant test vectors; no real session credentials.
    // Production MUST use independent OS-generated one-time secrets.
    let key = [0x11u8; 32];
    let challenge = [0x22u8; 32];
    let run = (|| {
        let bootstrap = json!({
            "protocol_version": 1,
            "operation": "bootstrap",
            "request_id": REQUEST_ID,
            "session_key": to_hex(&key),
            "challenge": to_hex(&challenge),
        }).to_string() + "\n";
        if bootstrap.len() > MAX_FRAME { return Err("frame_limit"); }
        stdin.write_all(bootstrap.as_bytes()).map_err(|_| "worker_io")?;
        stdin.flush().map_err(|_| "worker_io")?;
        let proof = receive.recv_timeout(WAIT).map_err(|_| "worker_timeout")??;
        verify_proof(&proof, &key, &challenge)?;

        // Only a validated fixed metadata operation can follow; no execution.
        let describe = json!({"protocol_version": 1, "operation": "describe", "request_id": REQUEST_ID})
            .to_string() + "\n";
        stdin.write_all(describe.as_bytes()).map_err(|_| "worker_io")?;
        stdin.flush().map_err(|_| "worker_io")?;
        let result = receive.recv_timeout(WAIT).map_err(|_| "worker_timeout")??;
        let value: Value = serde_json::from_slice(&result).map_err(|_| "invalid_result")?;
        if value["protocol_version"] != 1
            || value["operation"] != "describe_result"
            || value["request_id"] != REQUEST_ID
            || value["worker_state"] != "not_connected"
            || value["launch_enabled"] != false
            || value["connection_ready"] != false
            || value["cuda_tested"] != false
            || value["downloads_performed"] != false
        {
            return Err("invalid_result");
        }
        Ok(())
    })();

    // Always reclaim the full Job Object group, even after malformed proof,
    // EOF or timeouts. Never leave an owned Python subprocess alive.
    drop(stdin);
    let _ = job.terminate();
    let drained = job.verify_drained(Duration::from_secs(3)).is_ok();
    let _ = child.kill();
    let _ = child.wait();
    if !drained { return Err("worker_cleanup"); }
    run
}

#[test]
fn owned_fixture_roundtrip_is_cpu_only() {
    assert_eq!(execute_fixture("success"), Ok(()));
}

#[test]
fn fake_proof_and_overlong_reply_fail_closed() {
    assert_eq!(execute_fixture("tamper"), Err("invalid_proof"));
    assert_eq!(execute_fixture("oversize"), Err("frame_limit"));
}

#[test]
fn stalled_or_crashed_worker_is_reaped_without_gpu() {
    assert_eq!(execute_fixture("stall"), Err("worker_timeout"));
    assert_eq!(execute_fixture("crash"), Err("worker_eof"));
}

#[test]
fn hmac_test_implementation_matches_rfc_4231_vector() {
    // RFC 4231 case 1: 20 bytes of 0x0b with trailing zeros are equivalent
    // to the same 64-byte zero-padded HMAC key block.
    let mut key = [0u8; 32];
    key[..20].fill(0x0b);
    assert_eq!(to_hex(&hmac_test(&key, b"Hi There")),
        "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7");
}
