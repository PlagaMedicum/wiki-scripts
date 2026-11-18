use std::collections::HashSet;
use std::hash::Hash;
use std::sync::{Arc, Mutex};

#[derive(Clone, Default)]
pub struct KeyLockSet<K> {
    inner: Arc<Mutex<HashSet<K>>>,
}

pub struct KeyLockGuard<K>
where
    K: Eq + Hash + Clone,
{
    inner: Arc<Mutex<HashSet<K>>>,
    key: Option<K>,
}

impl<K> KeyLockSet<K>
where
    K: Eq + Hash + Clone,
{
    pub fn new() -> Self {
        Self {
            inner: Arc::new(Mutex::new(HashSet::new())),
        }
    }

    pub fn try_lock(&self, key: K) -> Option<KeyLockGuard<K>> {
        let mut guard = self.inner.lock().expect("lock set poisoned");
        if !guard.insert(key.clone()) {
            return None;
        }
        drop(guard);
        Some(KeyLockGuard {
            inner: Arc::clone(&self.inner),
            key: Some(key),
        })
    }
}

impl<K> Drop for KeyLockGuard<K>
where
    K: Eq + Hash + Clone,
{
    fn drop(&mut self) {
        if let Some(key) = self.key.take() {
            let mut guard = self.inner.lock().expect("lock set poisoned");
            let _ = guard.remove(&key);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lock_is_exclusive() {
        let locks = KeyLockSet::<u64>::new();
        let guard = locks.try_lock(42).unwrap();
        assert!(locks.try_lock(42).is_none());
        drop(guard);
        assert!(locks.try_lock(42).is_some());
    }
}
