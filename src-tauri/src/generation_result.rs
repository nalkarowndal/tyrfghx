//! M3-8: validate bounded CLI metrics and an existing fixed-root PNG.
//! No stdout text, absolute path or prompt is ever sent to the webview.
//! A checksum proves only that the saved bytes match the CLI report;
//! it is NOT an image-quality, CUDA-driver or prompt-compliance test.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File},
    io::{Read, BufReader},
    path::{Path, PathBuf},
};

pub const MAX_OUTPUT_JSON: usize = 16 * 1024;
const MAX_PNG_SIZE: u64 = 8 * 1024 * 1024;
const MAX_PIXEL_BYTES: usize = 16 * 1024 * 1024;
const MAX_REPORTED_VRAM: u64 = 256 * 1024 * 1024 * 1024;
const PNG_MAGIC: &[u8; 8] = b"\x89PNG\r\n\x1a\n";

#[derive(Clone, Debug, Serialize)]
pub struct VerifiedResult {
    pub file_name: String,
    pub png_sha256: String,
    pub seed: u64,
    pub elapsed_seconds: f64,
    pub peak_allocated_bytes: Option<u64>,
    pub peak_reserved_bytes: Option<u64>,
    pub measurement: String,
    pub validation: String,
    pub width: u32,
    pub height: u32,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CliReport {
    mode: String,
    output: String,
    seed: u64,
    metrics: CliMetrics,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CliMetrics {
    measurement_type: String,
    elapsed_seconds: f64,
    output_png_sha256: String,
    gpu_peak_allocated_bytes: Option<u64>,
    gpu_peak_reserved_bytes: Option<u64>,
    gpu_memory_measurement: String,
    caveat: String,
}

fn generated_png_name(name: &str) -> bool {
    name.len() == 44
        && name.starts_with("aiimage-") && name.ends_with(".png")
        && name.as_bytes()[8..40].iter().all(u8::is_ascii_hexdigit)
}

fn valid_digest(hash: &str) -> bool {
    hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit())
}

/// Decode one actual PNG frame under strict memory/dimension limits.
/// A header and a matching SHA-256 alone are insufficient: arbitrary bytes
/// could be written by the subprocess and hashed. This checks that the
/// image data itself can be decoded as a PNG, not its artistic quality.
fn decode_png(path: &Path) -> Result<(u32, u32), String> {
    let file = File::open(path).map_err(|_| "PNG 디코딩을 위해 파일을 열 수 없습니다.")?;
    let mut limits = png::Limits::default();
    limits.bytes = MAX_PIXEL_BYTES;
    let decoder = png::Decoder::new_with_limits(BufReader::new(file), limits);
    let mut reader = decoder.read_info()
        .map_err(|_| "PNG 파일의 헤더 또는 메타데이터가 손상되었습니다.")?;
    let info = reader.info();
    let (width, height) = (info.width, info.height);
    if !(1..=1024).contains(&width) || !(1..=1024).contains(&height) ||
       info.animation_control.is_some() {
        return Err("허용되지 않은 이미지 해상도 또는 애니메이션 PNG입니다.".into());
    }
    let capacity = reader.output_buffer_size().ok_or("PNG 디코딩 버퍼 크기를 계산할 수 없습니다.")?;
    if capacity == 0 || capacity > MAX_PIXEL_BYTES {
        return Err("PNG 디코딩 메모리 상한을 초과했습니다.".into());
    }
    let mut pixels = vec![0u8; capacity];
    let frame = reader.next_frame(&mut pixels)
        .map_err(|_| "PNG 압축 데이터 또는 무결성 검증에 실패했습니다.")?;
    if frame.width != width || frame.height != height || frame.buffer_size() > capacity {
        return Err("PNG 프레임의 크기나 디코딩 길이가 올바르지 않습니다.".into());
    }
    Ok((width, height))
}


pub fn validate_report(bytes: &[u8], root: &Path, seed: u64) -> Result<VerifiedResult, String> {
    if bytes.is_empty() || bytes.len() > MAX_OUTPUT_JSON {
        return Err("생성 실행기 출력이 없거나 크기 제한을 초과했습니다.".into());
    }
    let output: CliReport = serde_json::from_slice(bytes)
        .map_err(|_| "생성 실행기 결과 JSON이 올바르지 않습니다.")?;
    if output.mode != "generated_unverified" || output.seed != seed ||
        !valid_digest(&output.metrics.output_png_sha256) ||
        output.metrics.measurement_type != "real_cuda_allocator_if_available" ||
        !output.metrics.elapsed_seconds.is_finite() ||
        !(0.0..=3600.0).contains(&output.metrics.elapsed_seconds) ||
        output.metrics.caveat.len() > 400 ||
        !matches!(output.metrics.gpu_memory_measurement.as_str(),
            "torch_cuda_allocator" | "measurement_failed" | "unavailable")
    {
        return Err("생성 실행기 결과의 모델 또는 측정값 형식이 올바르지 않습니다.".into());
    }
    if [output.metrics.gpu_peak_allocated_bytes, output.metrics.gpu_peak_reserved_bytes]
        .iter().flatten().any(|v| *v > MAX_REPORTED_VRAM) ||
        (output.metrics.gpu_memory_measurement == "torch_cuda_allocator" &&
         (output.metrics.gpu_peak_allocated_bytes.is_none() ||
          output.metrics.gpu_peak_reserved_bytes.is_none())) ||
        matches!(
            (output.metrics.gpu_peak_allocated_bytes, output.metrics.gpu_peak_reserved_bytes),
            (Some(allocated), Some(reserved)) if allocated > reserved
        )
    {
        return Err("GPU 할당 메모리 측정값이 유효하지 않습니다.".into());
    }

    if root.is_symlink() || !root.is_dir() {
        return Err("로컬 결과 폴더가 없거나 안전하지 않습니다.".into());
    }
    let raw = PathBuf::from(&output.output);
    if !raw.is_absolute() {
        return Err("생성 파일 경로가 절대 경로가 아닙니다.".into());
    }
    let Some(file_name) = raw.file_name().and_then(|n| n.to_str()) else {
        return Err("생성 파일 이름이 올바르지 않습니다.".into());
    };
    if !generated_png_name(file_name) {
        return Err("허용되지 않은 생성 파일 이름입니다.".into());
    }
    let file_name = file_name.to_owned();
    let allowed = root.join(&file_name);
    if fs::symlink_metadata(&allowed)
        .map_err(|_| "결과 PNG를 찾지 못했습니다.")?.file_type().is_symlink()
    {
        return Err("심볼릭 링크 생성 결과는 허용하지 않습니다.".into());
    }
    let real_root = fs::canonicalize(root).map_err(|_| "결과 폴더를 확인할 수 없습니다.")?;
    let actual = fs::canonicalize(&raw).map_err(|_| "생성 결과 파일을 찾지 못했습니다.")?;
    if actual != real_root.join(&file_name) {
        return Err("프로젝트 외부의 결과 경로를 거부했습니다.".into());
    }
    let meta = fs::metadata(&actual).map_err(|_| "결과 파일을 읽을 수 없습니다.")?;
    if !meta.is_file() || meta.len() <= PNG_MAGIC.len() as u64 || meta.len() > MAX_PNG_SIZE {
        return Err("결과 PNG의 크기가 지원 범위를 벗어났습니다.".into());
    }
    let mut file = BufReader::new(File::open(&actual).map_err(|_| "결과 PNG를 열 수 없습니다.")?);
    let mut hasher = Sha256::new();
    let mut signature = [0u8; 8];
    file.read_exact(&mut signature).map_err(|_| "결과 PNG 헤더를 읽을 수 없습니다.")?;
    if &signature != PNG_MAGIC {
        return Err("파일에 PNG 시그니처가 없습니다.".into());
    }
    hasher.update(signature);
    let mut chunk = [0u8; 64 * 1024];
    loop {
        let count = file.read(&mut chunk).map_err(|_| "PNG 검증 중 읽기 오류가 발생했습니다.")?;
        if count == 0 { break; }
        hasher.update(&chunk[..count]);
    }
    let actual_hash = format!("{:x}", hasher.finalize());
    if !actual_hash.eq_ignore_ascii_case(&output.metrics.output_png_sha256) {
        return Err("생성 PNG의 SHA-256 값이 실행기 보고와 일치하지 않습니다.".into());
    }
    // Do not mark an image as valid until its compressed pixels decode.
    let (width, height) = decode_png(&actual)?;
    Ok(VerifiedResult {
        file_name,
        png_sha256: actual_hash,
        seed,
        elapsed_seconds: output.metrics.elapsed_seconds,
        peak_allocated_bytes: output.metrics.gpu_peak_allocated_bytes,
        peak_reserved_bytes: output.metrics.gpu_peak_reserved_bytes,
        measurement: output.metrics.gpu_memory_measurement,
        validation: "png_decoded_and_sha256_verified".into(),
        width,
        height,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn fixture() -> (tempfile::TempDir, Vec<u8>) {
        let dir = tempfile::tempdir().unwrap();
        let file_name = format!("aiimage-{}.png", "a".repeat(32));
        let output = dir.path().join(file_name);
        let mut f = File::create(&output).unwrap();
        drop(f);
        let file = File::create(&output).unwrap();
        let mut encoder = png::Encoder::new(file, 2, 2);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().unwrap();
        writer.write_image_data(&[255u8; 16]).unwrap();
        drop(writer);
        let hash = format!("{:x}", Sha256::digest(fs::read(&output).unwrap()));
        let report = serde_json::json!({
            "mode": "generated_unverified",
            "output": output.to_str().unwrap(),
            "seed": 42,
            "metrics": {
                "measurement_type": "real_cuda_allocator_if_available",
                "elapsed_seconds": 12.5,
                "output_png_sha256": hash,
                "gpu_peak_allocated_bytes": 3_000_000_000u64,
                "gpu_peak_reserved_bytes": 3_200_000_000u64,
                "gpu_memory_measurement": "torch_cuda_allocator",
                "caveat": "Allocator peak is not total VRAM usage."
            }
        });
        (dir, serde_json::to_vec(&report).unwrap())
    }

    #[test] fn validates_local_hash_and_mapped_only_fields() {
        let (dir, report) = fixture();
        let result = validate_report(&report, dir.path(), 42).unwrap();
        assert_eq!(result.seed, 42);
        assert_eq!(result.peak_reserved_bytes, Some(3_200_000_000));
        assert_eq!(result.validation, "png_decoded_and_sha256_verified");
        assert_eq!((result.width, result.height), (2, 2));
    }

    #[test] fn rejects_tampering_wrong_seed_and_unexpected_schema() {
        let (dir, report) = fixture();
        assert!(validate_report(&report, dir.path(), 7).is_err());
        let mut value: serde_json::Value = serde_json::from_slice(&report).unwrap();
        value["secret"] = serde_json::json!("do not forward");
        assert!(validate_report(&serde_json::to_vec(&value).unwrap(), dir.path(), 42).is_err());
        value.as_object_mut().unwrap().remove("secret");
        value["metrics"]["output_png_sha256"] = serde_json::json!("0".repeat(64));
        assert!(validate_report(&serde_json::to_vec(&value).unwrap(), dir.path(), 42).is_err());
    }

    #[test] fn rejects_external_or_bad_filenames_and_oversized_json() {
        let (dir, report) = fixture();
        assert!(validate_report(&vec![b'X'; MAX_OUTPUT_JSON+1], dir.path(), 42).is_err());
        let mut value: serde_json::Value = serde_json::from_slice(&report).unwrap();
        value["output"] = serde_json::json!(dir.path().join("unrelated.png"));
        assert!(validate_report(&serde_json::to_vec(&value).unwrap(), dir.path(), 42).is_err());
        value["output"] = serde_json::json!("../aiimage-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png");
        assert!(validate_report(&serde_json::to_vec(&value).unwrap(), dir.path(), 42).is_err());
    }

    #[test] fn rejects_image_tampering_and_fake_png_signature() {
        let (dir, report) = fixture();
        let output: CliReport = serde_json::from_slice(&report).unwrap();
        let path = PathBuf::from(output.output);
        fs::write(&path, b"not really png").unwrap();
        assert!(validate_report(&report, dir.path(), 42).is_err());
        fs::write(&path, [PNG_MAGIC.as_slice(), b"different content"].concat()).unwrap();
        assert!(validate_report(&report, dir.path(), 42).is_err());
    }

    #[test]
    fn correctly_hashed_but_malformed_png_is_not_a_valid_image() {
        let (dir, report) = fixture();
        let mut value: serde_json::Value = serde_json::from_slice(&report).unwrap();
        let path = PathBuf::from(value["output"].as_str().unwrap());
        let corrupt = [PNG_MAGIC.as_slice(), b"pretend pixels"].concat();
        fs::write(&path, &corrupt).unwrap();
        value["metrics"]["output_png_sha256"] =
            serde_json::json!(format!("{:x}", Sha256::digest(&corrupt)));
        assert!(validate_report(&serde_json::to_vec(&value).unwrap(), dir.path(), 42).is_err());
    }

    #[test] fn allows_unavailable_allocator_without_claiming_vram_measured() {
        let (dir, report) = fixture();
        let mut value: serde_json::Value = serde_json::from_slice(&report).unwrap();
        value["metrics"]["gpu_memory_measurement"] = serde_json::json!("unavailable");
        value["metrics"]["gpu_peak_allocated_bytes"] = serde_json::Value::Null;
        value["metrics"]["gpu_peak_reserved_bytes"] = serde_json::Value::Null;
        let result = validate_report(&serde_json::to_vec(&value).unwrap(), dir.path(), 42).unwrap();
        assert_eq!(result.peak_allocated_bytes, None);
    }
}
