class TaskMonitor:
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def on_progress_event(self):
        pass

    def on_timeout_expiry(self):
        pass

    def _raise_alert(self):
        pass

    def _cancel_request(self):
        pass
