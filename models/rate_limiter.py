import time
from collections import deque
from threading import Lock

class RateLimiter:
    """
    Thread-safe rate limiter with key rotation
    """
    def __init__(self, rpm_limit, num_keys=1):
        self.rpm_limit = rpm_limit
        self.num_keys = num_keys
        self.effective_rpm = rpm_limit * num_keys
        
        # Separate tracking per key
        self.request_times = {i: deque() for i in range(num_keys)}
        self.current_key_index = 0
        self.lock = Lock()
    
    def wait_if_needed(self):
        """
        Blocks until it's safe to make a request
        Returns the key index to use
        """
        with self.lock:
            current_time = time.time()
            
            # Try to find a key that's ready
            for attempt in range(self.num_keys):
                key_idx = (self.current_key_index + attempt) % self.num_keys
                times = self.request_times[key_idx]
                
                # Clean old requests (older than 60 seconds)
                while times and current_time - times[0] > 60:
                    times.popleft()
                
                # Check if this key has capacity
                if len(times) < self.rpm_limit:
                    times.append(current_time)
                    self.current_key_index = (key_idx + 1) % self.num_keys
                    return key_idx
            
            # All keys at limit - must wait
            oldest_time = min(
                times[0] for times in self.request_times.values() if times
            )
            sleep_time = 60 - (current_time - oldest_time) + 1
            
            print(f"⏳ Rate limit reached. Sleeping {sleep_time:.1f}s...")
            time.sleep(sleep_time)
            
            # Retry after sleep
            return self.wait_if_needed()
