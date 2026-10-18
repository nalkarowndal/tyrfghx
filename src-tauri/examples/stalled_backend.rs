//! Disposable regression fixture: never reads stdin or produces readiness.
//! It is never a bundle resource or reachable from production IPC.
fn main() {
    loop { std::thread::park(); }
}
