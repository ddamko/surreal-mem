"""FastAPI dependencies that hand routers the composition root."""

from typing import Annotated

from fastapi import Depends, Request

from surrealmem.bootstrap.container import AppContainer
from surrealmem.bootstrap.services import Services


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_services(request: Request) -> Services:
    return request.app.state.container.services


ContainerDep = Annotated[AppContainer, Depends(get_container)]
ServicesDep = Annotated[Services, Depends(get_services)]
