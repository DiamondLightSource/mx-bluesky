class LivenessService:
    """A service for reporting liveness of the external callback process."""

    def start(self, address: str, port: int):
        """Configure the service to periodically report it is alive
        Args:
            address: Address to bind liveness service to
            port: Port number to bind the liveness service to"""
        pass

    def report_error(self, message: str):
        """Report that an error has occurred
        Args:
            message: Details of the error encountered."""
        pass
