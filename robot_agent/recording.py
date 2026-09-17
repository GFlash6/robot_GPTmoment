"""MCAP message recording without inventing messages or sensor metadata."""

from mcap.writer import Writer
from mcap.reader import make_reader
from .contracts import require


class Recorder:
    def __init__(self, path):
        self.file = open(path, "xb")
        self.writer = Writer(self.file, enable_crcs=True)
        self.writer.start()
        self.channels = {}

    def append(
        self,
        topic,
        encoding,
        data,
        publish_time,
        log_time,
        metadata,
        schema_name="",
        schema_encoding="",
        schema_data=b"",
    ):
        require(isinstance(data, bytes), "record raw bytes without implicit conversion")
        require(
            all(type(t) is int and 0 <= t < 2**64 for t in (publish_time, log_time)),
            "MCAP timestamps must be uint64 nanoseconds",
        )
        require(
            isinstance(topic, str)
            and bool(topic)
            and isinstance(encoding, str)
            and bool(encoding),
            "topic and encoding required",
        )
        require(
            isinstance(metadata, dict)
            and all(
                isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()
            ),
            "MCAP channel metadata must be strings",
        )
        key = (
            topic,
            encoding,
            tuple(sorted(metadata.items())),
            schema_name,
            schema_encoding,
            schema_data,
        )
        if key not in self.channels:
            sid = (
                self.writer.register_schema(schema_name, schema_encoding, schema_data)
                if schema_name
                else 0
            )
            self.channels[key] = self.writer.register_channel(
                topic, encoding, sid, metadata
            )
        self.writer.add_message(self.channels[key], log_time, data, publish_time)

    def close(self):
        if not self.file.closed:
            try:
                self.writer.finish()
                self.file.flush()
                import os

                os.fsync(self.file.fileno())
            finally:
                self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def messages(path):
    with open(path, "rb") as stream:
        for schema, channel, message in make_reader(
            stream, validate_crcs=True
        ).iter_messages():
            yield {
                "topic": channel.topic,
                "encoding": channel.message_encoding,
                "metadata": channel.metadata,
                "schema": schema,
                "data": message.data,
                "publish_time": message.publish_time,
                "log_time": message.log_time,
            }
