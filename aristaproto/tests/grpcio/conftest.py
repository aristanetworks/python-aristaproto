from __future__ import annotations

import pytest

from tests.grpcio.fixtures import make_generated_style_base, service_output
from tests.util import requires_grpcio  # noqa: F401


@pytest.fixture
def grpcio_test_base(requires_grpcio):
    return make_generated_style_base()


@pytest.fixture
def grpcio_working_service(grpcio_test_base):
    class WorkingService(grpcio_test_base):
        async def do_thing(self, message):
            do_thing_response_type = service_output().DoThingResponse

            return do_thing_response_type(names=[message.name])

        async def do_many_things(self, messages):
            do_thing_response_type = service_output().DoThingResponse

            return do_thing_response_type(names=[message.name async for message in messages])

        async def get_thing_versions(self, message):
            get_thing_response_type = service_output().GetThingResponse

            for version in range(1, 4):
                yield get_thing_response_type(name=message.name, version=version)

        async def get_different_things(self, messages):
            get_thing_response_type = service_output().GetThingResponse

            version = 0
            async for message in messages:
                version += 1
                yield get_thing_response_type(name=message.name, version=version)

    return WorkingService()
