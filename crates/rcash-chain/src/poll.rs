//! Polling policy for deploy status and finality.

use std::time::Duration;

/// How long and how often to poll.
///
/// The interval grows exponentially to `max_interval`, and each attempt adds a
/// deterministic per-caller jitter derived from the deploy/block id. The jitter
/// is not cryptographic: it exists to stop a fleet of clients retrying in lockstep
/// after a node sheds work with `Retry-After`.
#[derive(Clone, Copy, Debug)]
pub struct PollPolicy {
    pub interval: Duration,
    pub timeout: Duration,
    pub max_interval: Duration,
}

impl Default for PollPolicy {
    fn default() -> Self {
        Self {
            interval: Duration::from_millis(250),
            timeout: Duration::from_secs(120),
            max_interval: Duration::from_secs(8),
        }
    }
}

impl PollPolicy {
    /// A fixed-interval policy, kept for callers that need the old behaviour.
    pub fn new(interval: Duration, timeout: Duration) -> Self {
        Self {
            interval,
            timeout,
            max_interval: interval,
        }
    }

    /// The number of attempts this policy allows at the initial interval.
    pub fn attempts(&self) -> u32 {
        let interval = self.interval.as_millis().max(1);
        (self.timeout.as_millis() / interval).max(1) as u32
    }

    /// The delay before attempt `attempt` (zero-based), bounded by `max_interval`.
    ///
    /// `seed` is any stable per-caller value (a deploy id or block hash); it spreads
    /// retries across callers without requiring a random-number dependency.
    pub fn delay(&self, attempt: u32, seed: &str) -> Duration {
        let base = self.interval.as_millis() as u64;
        let cap = self.max_interval.as_millis() as u64;
        let exponential = base.saturating_mul(1u64 << attempt.min(8)).min(cap.max(1));
        let mixed =
            fnv1a(seed).wrapping_add(u64::from(attempt).wrapping_mul(0x9e37_79b9_7f4a_7c15));
        let jitter = if exponential > 1 {
            mixed % (exponential / 2 + 1)
        } else {
            0
        };
        Duration::from_millis(exponential + jitter)
    }
}

fn fnv1a(text: &str) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325u64;
    for byte in text.as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    hash
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn delay_is_bounded_for_every_attempt() {
        let policy = PollPolicy::default();
        let cap = policy.max_interval.as_millis() as u64;
        for attempt in 0..12 {
            let delay = policy.delay(attempt, "deploy-id").as_millis() as u64;
            assert!(delay >= policy.interval.as_millis() as u64);
            assert!(delay <= cap + cap / 2);
        }
    }

    #[test]
    fn delay_depends_on_the_caller_seed() {
        let policy = PollPolicy::default();
        assert_ne!(
            policy.delay(4, "a").as_millis(),
            policy.delay(4, "b").as_millis()
        );
    }
}
