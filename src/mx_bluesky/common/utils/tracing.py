from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracing(service_name: str = "Hyperion"):
    resource = Resource(attributes={SERVICE_NAME: service_name})

    trace_provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint="http://0.0.0.0:4318/v1/traces")
    )
    trace_provider.add_span_processor(processor)
    trace.set_tracer_provider(trace_provider)

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint="http://0.0.0.0:4318/v1/metrics")
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)


TRACER = trace.get_tracer(__name__)
