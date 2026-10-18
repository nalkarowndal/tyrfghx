//! M3-5: Windows OS-managed process group for a fixed local Python CLI.
//! The Python process is created suspended, added to a kill-on-close Job
//! Object, and *only then* resumed. No user-supplied executable or shell.

#[cfg(windows)]
mod platform {
    use std::{
        io, mem,
        os::windows::{io::AsRawHandle, process::CommandExt},
        process::{Child, Command},
        ptr,
        thread,
        time::{Duration, Instant},
    };
    use windows_sys::Win32::{
        Foundation::{CloseHandle, HANDLE, INVALID_HANDLE_VALUE},
        System::{
            Diagnostics::ToolHelp::{
                CreateToolhelp32Snapshot, Thread32First, Thread32Next, THREADENTRY32,
                TH32CS_SNAPTHREAD,
            },
            JobObjects::{
                AssignProcessToJobObject, CreateJobObjectW, SetInformationJobObject,
                QueryInformationJobObject, TerminateJobObject,
                JobObjectBasicAccountingInformation, JobObjectExtendedLimitInformation,
                JOBOBJECT_BASIC_ACCOUNTING_INFORMATION, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            },
            Threading::{
                OpenThread, ResumeThread, CREATE_SUSPENDED, THREAD_SUSPEND_RESUME,
            },
        },
    };

    struct OwnedHandle(HANDLE);
    // Win32 HANDLEs are kernel references that support use/close across threads;
    // this wrapper uniquely owns its handle and never duplicates its ownership.
    unsafe impl Send for OwnedHandle {}
    unsafe impl Sync for OwnedHandle {}
    impl Drop for OwnedHandle {
        fn drop(&mut self) {
            if !self.0.is_null() && self.0 != INVALID_HANDLE_VALUE {
                unsafe { CloseHandle(self.0); }
            }
        }
    }

    pub struct ProcessJob {
        handle: OwnedHandle,
    }

    pub fn prepare_command(command: &mut Command) {
        command.creation_flags(CREATE_SUSPENDED);
    }

    fn resume_primary_thread(pid: u32) -> Result<(), String> {
        let snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) };
        if snapshot == INVALID_HANDLE_VALUE {
            return Err(format!("Cannot enumerate suspended process threads: {}", io::Error::last_os_error()));
        }
        let snapshot = OwnedHandle(snapshot);
        let mut entry = THREADENTRY32 {
            dwSize: mem::size_of::<THREADENTRY32>() as u32,
            ..THREADENTRY32::default()
        };
        if unsafe { Thread32First(snapshot.0, &mut entry) } == 0 {
            return Err(format!("No process threads could be enumerated: {}", io::Error::last_os_error()));
        }
        loop {
            if entry.th32OwnerProcessID == pid {
                let thread = unsafe { OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID) };
                if thread.is_null() {
                    return Err(format!("Cannot open suspended Python thread: {}", io::Error::last_os_error()));
                }
                let thread = OwnedHandle(thread);
                let result = unsafe { ResumeThread(thread.0) };
                if result == u32::MAX {
                    return Err(format!("Cannot resume Python main thread: {}", io::Error::last_os_error()));
                }
                if result != 1 {
                    return Err(format!("Unexpected Python thread suspend count: {result}"));
                }
                return Ok(());
            }
            if unsafe { Thread32Next(snapshot.0, &mut entry) } == 0 { break; }
        }
        Err("Suspended Python main thread was not found".into())
    }

    impl ProcessJob {
        pub fn attach_and_resume(child: &mut Child) -> Result<Self, String> {
            let raw = unsafe { CreateJobObjectW(ptr::null(), ptr::null()) };
            if raw.is_null() {
                return Err(format!("Cannot create Windows Job Object: {}", io::Error::last_os_error()));
            }
            let instance = Self { handle: OwnedHandle(raw) };
            let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let configured = unsafe {
                SetInformationJobObject(
                    instance.handle.0,
                    JobObjectExtendedLimitInformation,
                    &limits as *const _ as *const _,
                    mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                )
            };
            if configured == 0 {
                return Err(format!("Cannot configure job cleanup: {}", io::Error::last_os_error()));
            }
            let assigned = unsafe {
                AssignProcessToJobObject(instance.handle.0, child.as_raw_handle() as HANDLE)
            };
            if assigned == 0 {
                return Err(format!("Cannot assign Python to job: {}", io::Error::last_os_error()));
            }
            // Assignment occurs before Python executes a single user-space
            // instruction, avoiding the spawn-before-assignment race.
            resume_primary_thread(child.id())?;
            Ok(instance)
        }

        pub fn terminate(&self) -> Result<(), String> {
            if unsafe { TerminateJobObject(self.handle.0, 1) } == 0 {
                return Err(format!("Could not terminate Windows process group: {}", io::Error::last_os_error()));
            }
            Ok(())
        }

        /// Query the whole Windows job, not merely the Python parent PID.
        /// Calling TerminateJobObject only requests synchronous termination
        /// of the group; only ActiveProcesses == 0 confirms no descendants
        /// remain associated with this Job Object.
        pub fn verify_drained(&self, limit: Duration) -> Result<(), String> {
            let started = Instant::now();
            loop {
                let mut accounting = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION::default();
                let query = unsafe {
                    QueryInformationJobObject(
                        self.handle.0,
                        JobObjectBasicAccountingInformation,
                        &mut accounting as *mut _ as *mut _,
                        mem::size_of::<JOBOBJECT_BASIC_ACCOUNTING_INFORMATION>() as u32,
                        ptr::null_mut(),
                    )
                };
                if query == 0 {
                    return Err("Windows 작업 그룹의 프로세스 종료 상태를 조회하지 못했습니다.".into());
                }
                if accounting.ActiveProcesses == 0 {
                    return Ok(());
                }
                if started.elapsed() >= limit {
                    return Err("종료 요청 후에도 Windows 작업 그룹에 실행 중인 프로세스가 남아 있습니다.".into());
                }
                thread::sleep(Duration::from_millis(50));
            }
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        #[test]
        fn suspended_fixture_is_assigned_before_resuming() {
            // No CUDA or model weights. This exercises the real Win32 APIs.
            let mut cmd = Command::new("cmd.exe");
            cmd.args(["/C", "exit /B 0"]);
            cmd.stdin(std::process::Stdio::null())
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null());
            prepare_command(&mut cmd);
            let mut child = cmd.spawn().unwrap();
            let group = match ProcessJob::attach_and_resume(&mut child) {
                Ok(job) => job,
                Err(reason) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    panic!("Windows job assignment failed: {reason}");
                }
            };
            assert!(child.wait().unwrap().success());
            group.terminate().unwrap();
        }

        #[test]
        fn cleanup_verification_checks_live_and_terminated_group() {
            let mut cmd = Command::new("cmd.exe");
            cmd.args(["/C", "ping -n 25 127.0.0.1 >nul"]);
            cmd.stdin(std::process::Stdio::null())
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null());
            prepare_command(&mut cmd);
            let mut child = cmd.spawn().unwrap();
            let group = match ProcessJob::attach_and_resume(&mut child) {
                Ok(job) => job,
                Err(reason) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    panic!("Windows job assignment failed: {reason}");
                }
            };
            assert!(group.verify_drained(Duration::from_millis(100)).is_err());
            group.terminate().unwrap();
            assert!(group.verify_drained(Duration::from_secs(2)).is_ok());
            assert!(!child.wait().unwrap().success());
        }

        #[test]
        fn termination_finishes_live_fixture() {
            let mut cmd = Command::new("cmd.exe");
            cmd.args(["/C", "ping -n 25 127.0.0.1 >nul"]);
            cmd.stdin(std::process::Stdio::null())
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null());
            prepare_command(&mut cmd);
            let mut child = cmd.spawn().unwrap();
            let group = match ProcessJob::attach_and_resume(&mut child) {
                Ok(job) => job,
                Err(reason) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    panic!("Windows job assignment failed: {reason}");
                }
            };
            group.terminate().unwrap();
            assert!(!child.wait().unwrap().success());
        }
    }
}

#[cfg(not(windows))]
mod platform {
    use std::process::{Child, Command};
    pub struct ProcessJob;
    pub fn prepare_command(_: &mut Command) {}
    impl ProcessJob {
        pub fn attach_and_resume(_: &mut Child) -> Result<Self, String> {
            Err("Windows Job Objects are unavailable on this platform".into())
        }
        pub fn terminate(&self) -> Result<(), String> {
            Err("Windows Job Objects are unavailable on this platform".into())
        }
        pub fn verify_drained(&self, _: std::time::Duration) -> Result<(), String> {
            Err("Windows Job Objects are unavailable on this platform".into())
        }
    }
}

pub use platform::{prepare_command, ProcessJob};
