//! M3-12: conservative *desktop* VRAM preflight for explicitly approved jobs.
//! Matches M3-11 acceptance-CLI heuristics. No model load, network access or
//! remote telemetry. Point-in-time readings never guarantee inference success.

const GIB: u64 = 1024 * 1024 * 1024;
const MAX_VRAM: u64 = 256 * GIB;
const MIN_TOTAL: u64 = 6 * GIB;
const MIN_FREE: u64 = 4 * GIB;
const MAX_LOW_VRAM_PIXELS: u64 = 768 * 768;

/// Return a truthful warning when an explicitly acknowledged risky trial
/// was allowed, otherwise reject risky or invalid GPU observations.
pub(crate) fn check_trial(
    total: u64, free: u64, width: u32, height: u32, risk_acknowledged: bool,
) -> Result<Option<String>, String> {
    if total == 0 || total > MAX_VRAM || free > total {
        return Err("CUDA 메모리 진단값이 올바르지 않아 생성을 차단했습니다.".into());
    }
    if !(512..=1024).contains(&width) || !(512..=1024).contains(&height)
        || width % 64 != 0 || height % 64 != 0 {
        return Err("GPU VRAM 검사에 지원되지 않는 이미지 크기입니다.".into());
    }

    let mut reasons = Vec::new();
    if total < MIN_TOTAL { reasons.push("전체 VRAM 6GiB 미만"); }
    if free < MIN_FREE { reasons.push("현재 가용 VRAM 4GiB 미만"); }
    if total <= 8 * GIB && u64::from(width) * u64::from(height) > MAX_LOW_VRAM_PIXELS {
        reasons.push("8GiB 이하 GPU에서 768×768 초과 요청");
    }
    if reasons.is_empty() { return Ok(None); }
    if !risk_acknowledged {
        return Err(format!(
            "GPU 안전 사전 검사로 실행을 차단했습니다: {}. 불필요한 GPU 프로그램을 종료하거나 512×512로 낮추세요. 위험을 이해한 경우에만 별도 VRAM 위험 동의를 선택하세요.",
            reasons.join(", ")
        ));
    }
    Ok(Some(format!(
        "추가 VRAM 위험을 명시적으로 수락했습니다 ({}). 메모리 부족으로 생성에 실패할 수 있습니다.",
        reasons.join(", ")
    )))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normal_8gib_512_trial_is_only_permitted_not_guaranteed() {
        assert_eq!(check_trial(8 * GIB, 6 * GIB, 512, 512, false).unwrap(), None);
        assert_eq!(check_trial(8 * GIB, 4 * GIB, 768, 768, false).unwrap(), None);
    }

    #[test]
    fn free_memory_under_4gib_is_blocked_without_extra_opt_in() {
        let err = check_trial(8 * GIB, 3 * GIB, 512, 512, false).unwrap_err();
        assert!(err.contains("4GiB"));
        assert!(check_trial(8 * GIB, 3 * GIB, 512, 512, true)
            .unwrap().unwrap().contains("수락"));
    }

    #[test]
    fn low_total_memory_and_high_resolution_are_independently_blocked() {
        assert!(check_trial(5 * GIB, 5 * GIB, 512, 512, false).is_err());
        assert!(check_trial(8 * GIB, 7 * GIB, 1024, 1024, false).is_err());
        assert!(check_trial(8 * GIB, 7 * GIB, 1024, 1024, true)
            .unwrap().unwrap().contains("768×768"));
        assert!(check_trial(12 * GIB, 11 * GIB, 1024, 1024, false).is_ok());
    }

    #[test]
    fn malformed_or_contradictory_cuda_readings_are_not_bypassable() {
        for (total, free) in [(0, 0), (8 * GIB, 9 * GIB), (MAX_VRAM + 1, 4 * GIB)] {
            assert!(check_trial(total, free, 512, 512, false).is_err());
            assert!(check_trial(total, free, 512, 512, true).is_err());
        }
    }

    #[test]
    fn unsupported_dimensions_are_rejected_even_with_opt_in() {
        assert!(check_trial(8 * GIB, 8 * GIB, 513, 512, true).is_err());
        assert!(check_trial(8 * GIB, 8 * GIB, 2048, 2048, true).is_err());
    }
}
