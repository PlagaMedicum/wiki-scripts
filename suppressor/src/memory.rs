use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct MemorySnapshot {
    pub sampled_at: Option<DateTime<Utc>>,
    pub process: ProcessMemorySnapshot,
    pub cgroup: CgroupMemorySnapshot,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct ProcessMemorySnapshot {
    pub vm_rss_bytes: Option<u64>,
    pub vm_hwm_bytes: Option<u64>,
    pub error: Option<String>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct CgroupMemorySnapshot {
    pub current_bytes: Option<u64>,
    pub peak_bytes: Option<u64>,
    pub max_bytes: Option<u64>,
    pub max_is_unlimited: bool,
    pub events: Option<CgroupMemoryEvents>,
    pub error: Option<String>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default)]
pub struct CgroupMemoryEvents {
    pub low: u64,
    pub high: u64,
    pub max: u64,
    pub oom: u64,
    pub oom_kill: u64,
    pub oom_group_kill: u64,
}

/// Returns one best-effort point-in-time sample; telemetry failure is represented in the snapshot.
pub fn sample_memory_snapshot() -> MemorySnapshot {
    sample_memory_snapshot_from_paths(Path::new("/proc/self/status"), Path::new("/sys/fs/cgroup"))
}

fn sample_memory_snapshot_from_paths(proc_status: &Path, cgroup_dir: &Path) -> MemorySnapshot {
    MemorySnapshot {
        sampled_at: Some(Utc::now()),
        process: sample_process_memory(proc_status),
        cgroup: sample_cgroup_memory(cgroup_dir),
    }
}

fn sample_process_memory(path: &Path) -> ProcessMemorySnapshot {
    let raw = match fs::read_to_string(path) {
        Ok(raw) => raw,
        Err(error) => {
            return ProcessMemorySnapshot {
                error: Some(format!("failed to read {}: {error}", path.display())),
                ..ProcessMemorySnapshot::default()
            };
        }
    };
    let vm_rss_bytes = proc_status_kibibytes(&raw, "VmRSS").map(|value| value * 1024);
    let vm_hwm_bytes = proc_status_kibibytes(&raw, "VmHWM").map(|value| value * 1024);
    let mut missing = Vec::new();
    if vm_rss_bytes.is_none() {
        missing.push("VmRSS");
    }
    if vm_hwm_bytes.is_none() {
        missing.push("VmHWM");
    }
    ProcessMemorySnapshot {
        vm_rss_bytes,
        vm_hwm_bytes,
        error: (!missing.is_empty()).then(|| format!("missing {}", missing.join(", "))),
    }
}

fn proc_status_kibibytes(raw: &str, name: &str) -> Option<u64> {
    raw.lines().find_map(|line| {
        let value = line
            .strip_prefix(name)?
            .strip_prefix(':')?
            .split_whitespace()
            .next()?;
        value.parse().ok()
    })
}

fn sample_cgroup_memory(dir: &Path) -> CgroupMemorySnapshot {
    let mut errors = Vec::new();
    let current_bytes = read_cgroup_u64(dir, "memory.current", &mut errors);
    let peak_bytes = read_cgroup_u64(dir, "memory.peak", &mut errors);
    let max_raw = read_cgroup_text(dir, "memory.max", &mut errors);
    let (max_bytes, max_is_unlimited) = match max_raw.as_deref() {
        Some("max") => (None, true),
        Some(value) => match value.parse() {
            Ok(value) => (Some(value), false),
            Err(error) => {
                errors.push(format!("invalid memory.max: {error}"));
                (None, false)
            }
        },
        None => (None, false),
    };
    let events = read_cgroup_events(dir, &mut errors);
    CgroupMemorySnapshot {
        current_bytes,
        peak_bytes,
        max_bytes,
        max_is_unlimited,
        events,
        error: (!errors.is_empty()).then(|| errors.join("; ")),
    }
}

fn read_cgroup_u64(dir: &Path, name: &str, errors: &mut Vec<String>) -> Option<u64> {
    let value = read_cgroup_text(dir, name, errors)?;
    match value.parse() {
        Ok(value) => Some(value),
        Err(error) => {
            errors.push(format!("invalid {name}: {error}"));
            None
        }
    }
}

fn read_cgroup_text(dir: &Path, name: &str, errors: &mut Vec<String>) -> Option<String> {
    let path = dir.join(name);
    match fs::read_to_string(&path) {
        Ok(value) => Some(value.trim().to_string()),
        Err(error) => {
            errors.push(format!("failed to read {}: {error}", path.display()));
            None
        }
    }
}

fn read_cgroup_events(dir: &Path, errors: &mut Vec<String>) -> Option<CgroupMemoryEvents> {
    let raw = read_cgroup_text(dir, "memory.events", errors)?;
    let values = raw
        .lines()
        .filter_map(|line| {
            let (name, value) = line.split_once(' ')?;
            Some((name, value.parse::<u64>().ok()?))
        })
        .collect::<BTreeMap<_, _>>();
    let required = ["low", "high", "max", "oom", "oom_kill", "oom_group_kill"];
    let missing = required
        .iter()
        .copied()
        .filter(|name| !values.contains_key(name))
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        errors.push(format!("memory.events missing {}", missing.join(", ")));
        return None;
    }
    Some(CgroupMemoryEvents {
        low: values["low"],
        high: values["high"],
        max: values["max"],
        oom: values["oom"],
        oom_kill: values["oom_kill"],
        oom_group_kill: values["oom_group_kill"],
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn memory_snapshot_parses_proc_and_cgroup_v2_fixtures() {
        let temp = tempfile::tempdir().unwrap();
        let proc_status = temp.path().join("status");
        let cgroup = temp.path().join("cgroup");
        fs::create_dir(&cgroup).unwrap();
        fs::write(
            &proc_status,
            "Name:\tsuppressor\nVmRSS:\t  14 kB\nVmHWM:\t  20 kB\n",
        )
        .unwrap();
        fs::write(cgroup.join("memory.current"), "17\n").unwrap();
        fs::write(cgroup.join("memory.peak"), "18\n").unwrap();
        fs::write(cgroup.join("memory.max"), "536870912\n").unwrap();
        fs::write(
            cgroup.join("memory.events"),
            "low 0\nhigh 1\nmax 2\noom 3\noom_kill 4\noom_group_kill 5\n",
        )
        .unwrap();

        let snapshot = sample_memory_snapshot_from_paths(&proc_status, &cgroup);

        assert_eq!(snapshot.process.vm_rss_bytes, Some(14 * 1024));
        assert_eq!(snapshot.process.vm_hwm_bytes, Some(20 * 1024));
        assert!(snapshot.process.error.is_none());
        assert_eq!(snapshot.cgroup.current_bytes, Some(17));
        assert_eq!(snapshot.cgroup.peak_bytes, Some(18));
        assert_eq!(snapshot.cgroup.max_bytes, Some(536870912));
        assert!(!snapshot.cgroup.max_is_unlimited);
        assert_eq!(
            snapshot
                .cgroup
                .events
                .as_ref()
                .map(|events| events.oom_kill),
            Some(4)
        );
        assert!(snapshot.cgroup.error.is_none());
    }

    #[test]
    fn memory_snapshot_accepts_unlimited_cgroup_max() {
        let temp = tempfile::tempdir().unwrap();
        let proc_status = temp.path().join("missing-status");
        let cgroup = temp.path().join("cgroup");
        fs::create_dir(&cgroup).unwrap();
        fs::write(cgroup.join("memory.current"), "0\n").unwrap();
        fs::write(cgroup.join("memory.peak"), "0\n").unwrap();
        fs::write(cgroup.join("memory.max"), "max\n").unwrap();
        fs::write(
            cgroup.join("memory.events"),
            "low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0\n",
        )
        .unwrap();

        let snapshot = sample_memory_snapshot_from_paths(&proc_status, &cgroup);

        assert_eq!(snapshot.cgroup.current_bytes, Some(0));
        assert_eq!(snapshot.cgroup.peak_bytes, Some(0));
        assert_eq!(snapshot.cgroup.max_bytes, None);
        assert!(snapshot.cgroup.max_is_unlimited);
    }

    #[test]
    fn memory_snapshot_reports_missing_or_unreadable_telemetry_without_failure() {
        let temp = tempfile::tempdir().unwrap();
        let proc_status = temp.path().join("status");
        let cgroup = temp.path().join("missing-cgroup");
        fs::write(&proc_status, "VmRSS:\t  14 kB\n").unwrap();

        let snapshot = sample_memory_snapshot_from_paths(&proc_status, &cgroup);

        assert_eq!(snapshot.process.vm_rss_bytes, Some(14 * 1024));
        assert_eq!(snapshot.process.vm_hwm_bytes, None);
        assert_eq!(snapshot.process.error.as_deref(), Some("missing VmHWM"));
        assert!(snapshot.cgroup.current_bytes.is_none());
        assert!(snapshot.cgroup.events.is_none());
        assert!(snapshot.cgroup.error.is_some());
    }
}
