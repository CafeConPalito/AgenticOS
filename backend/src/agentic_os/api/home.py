from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from agentic_os.db.session import get_session
from agentic_os.schemas.home import HomeRead
from agentic_os.services import home

router = APIRouter(tags=["home"])
DbSession = Annotated[Session, Depends(get_session)]


@router.get("/home")
def get_home(db: DbSession) -> HomeRead:
    return home.build(db)
