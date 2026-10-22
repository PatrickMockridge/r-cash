//! Polling policy for deploy status and finality.

use std::time::Duration;

/// How long and how often to poll.
#[derive(Clone, Copy, Debug)]
pub struct PollPolicy {
    pub interval: Duration,
    pub timeout: Duration,
}

impl Default for PollPolicy {
    fn default() -> Self {
        Self {
            interval: Duration::from_millis(500),
            timeout: Duration::from_secs(60),
        }
    }
}

impl PollPolicy {
    pub fn new(interval: Duration, timeout: Duration) -> Self {
        Self { interval, timeout }
    }

    /// The number of attempts this policy allows.
    pub fn attempts(&self) -> u32 {
        let interval = self.interval.as_millis().max(1);
        (self.timeout.as_millis() / interval).max(1) as u32
    }
}
