"""Teams and their memberships (administrators only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select

from ...core.deps import DbSession, get_current_admin
from ...models import Team, TeamMember, User
from ...schemas import IdList, TeamCreate, TeamUpdate
from ...serializers import serialize_team

router = APIRouter(
    prefix="/teams", tags=["teams"], dependencies=[Depends(get_current_admin)]
)


async def _member_ids(db: DbSession, team_id: int) -> list[int]:
    rows = await db.scalars(
        select(TeamMember.user_id).where(TeamMember.team_id == team_id)
    )
    return list(rows)


async def _get_team(db: DbSession, team_id: int) -> Team:
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


async def _replace_members(db: DbSession, team: Team, user_ids: list[int]) -> None:
    """Make the team membership exactly ``user_ids``."""
    await db.execute(delete(TeamMember).where(TeamMember.team_id == team.id))
    known = set(
        (await db.scalars(select(User.id).where(User.id.in_(user_ids or [-1])))).all()
    )
    for user_id in dict.fromkeys(user_ids):
        if user_id in known:
            db.add(TeamMember(team_id=team.id, user_id=user_id))
    await db.flush()


@router.get("")
async def list_teams(db: DbSession) -> list[dict]:
    teams = (await db.scalars(select(Team).order_by(Team.name))).all()
    return [serialize_team(t, await _member_ids(db, t.id)) for t in teams]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(payload: TeamCreate, db: DbSession) -> dict:
    if await db.scalar(select(Team).where(Team.name == payload.name)):
        raise HTTPException(status_code=409, detail="A team with that name exists")
    team = Team(
        name=payload.name,
        description=payload.description,
        allow_auto_assign=payload.allow_auto_assign,
    )
    db.add(team)
    await db.flush()
    await _replace_members(db, team, payload.member_ids)
    return serialize_team(team, await _member_ids(db, team.id))


@router.patch("/{team_id}")
async def update_team(team_id: int, payload: TeamUpdate, db: DbSession) -> dict:
    team = await _get_team(db, team_id)
    data = payload.model_dump(exclude_unset=True)
    member_ids = data.pop("member_ids", None)
    for field, value in data.items():
        setattr(team, field, value)
    await db.flush()
    if member_ids is not None:
        await _replace_members(db, team, member_ids)
    return serialize_team(team, await _member_ids(db, team.id))


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(team_id: int, db: DbSession) -> None:
    team = await _get_team(db, team_id)
    await db.delete(team)
    await db.flush()


@router.put("/{team_id}/members")
async def set_members(team_id: int, payload: IdList, db: DbSession) -> dict:
    team = await _get_team(db, team_id)
    await _replace_members(db, team, payload.user_ids)
    return serialize_team(team, await _member_ids(db, team.id))
