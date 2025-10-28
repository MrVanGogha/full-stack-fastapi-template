import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.models import Item, ItemCreate, ItemUpdate, ItemPublic, ItemsPublic, Message, ItemTrashPublic, ItemsTrashPublic

from datetime import datetime, timedelta
from app import crud

router = APIRouter(prefix="/items", tags=["items"])


@router.post("/", response_model=ItemPublic)
def create_item(
    session: SessionDep, current_user: CurrentUser, item_in: ItemCreate
) -> Any:
    """
    创建一个新的物品，关联当前用户作为所有者。

    """
    item = crud.create_item(session=session, item_in=item_in, owner_id=current_user.id)
    return item


@router.get("/", response_model=ItemsPublic)
def read_items(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """
    检索所有物品（排除已软删除的物品）。
    Retrieve items (exclude soft-deleted).
    """

    if current_user.is_superuser:
        count_statement = select(func.count()).select_from(Item).where(Item.deleted_at == None)  # type: ignore
        count = session.exec(count_statement).one()
        statement = (
            select(Item)
            .where(Item.deleted_at == None)  # type: ignore
            .offset(skip)
            .limit(limit)
        )
        items = session.exec(statement).all()
    else:
        count_statement = (
            select(func.count())
            .select_from(Item)
            .where((Item.owner_id == current_user.id) & (Item.deleted_at == None))  # type: ignore
        )
        count = session.exec(count_statement).one()
        statement = (
            select(Item)
            .where((Item.owner_id == current_user.id) & (Item.deleted_at == None))  # type: ignore
            .offset(skip)
            .limit(limit)
        )
        items = session.exec(statement).all()

    return ItemsPublic(data=items, count=count)


@router.get("/trash", response_model=ItemsTrashPublic)
def read_trash_items(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> ItemsTrashPublic:
    """
    检索当前用户的所有已软删除物品（管理员可以查看所有用户的物品）。
    List items in trash for current user (admin sees all).
    Returns raw dict with deleted_at and expires_at.
    """
    retention_days = getattr(settings, "TRASH_RETENTION_DAYS", 7)
    if current_user.is_superuser:
        count_statement = select(func.count()).select_from(Item).where(Item.deleted_at != None)  # type: ignore
        count = session.exec(count_statement).one()
        statement = (
            select(Item)
            .where(Item.deleted_at != None)  # type: ignore
            .order_by(Item.deleted_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items = session.exec(statement).all()
    else:
        count_statement = (
            select(func.count())
            .select_from(Item)
            .where((Item.owner_id == current_user.id) & (Item.deleted_at != None))  # type: ignore
        )
        count = session.exec(count_statement).one()
        statement = (
            select(Item)
            .where((Item.owner_id == current_user.id) & (Item.deleted_at != None))  # type: ignore
            .order_by(Item.deleted_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items = session.exec(statement).all()

    data = []
    for it in items:
        expires_at = (it.deleted_at + timedelta(days=retention_days)) if it.deleted_at else None
        data.append(ItemTrashPublic(
            id=it.id,
            owner_id=it.owner_id,
            title=it.title,
            description=it.description,
            deleted_at=it.deleted_at,
            deleted_by=it.deleted_by,
            delete_reason=it.delete_reason,
            expires_at=expires_at,
        ))
    return ItemsTrashPublic(data=data, count=count)


@router.get("/{id}", response_model=ItemPublic)
def read_item(session: SessionDep, current_user: CurrentUser, id: uuid.UUID) -> Any:
    """
    Get item by ID (404 if soft-deleted).
    """
    item = session.get(Item, id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    return item

@router.post("/{id}/restore", response_model=ItemPublic)
def restore_item(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Any:
    """
    Restore a soft-deleted item.
    """
    item = session.get(Item, id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    if item.deleted_at is None:
        raise HTTPException(status_code=400, detail="Item is not in trash")
    item.deleted_at = None
    item.deleted_by = None
    item.delete_reason = None
    session.add(item)
    session.commit()
    session.refresh(item)
    return item

@router.delete("/{id}", response_model=Message)
def delete_item(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Message:
    """
    Soft delete an item (move to trash).
    """
    item = session.get(Item, id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    if item.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Item already in trash")
    item.deleted_at = datetime.utcnow()
    item.deleted_by = current_user.id
    session.add(item)
    session.commit()
    return Message(message="Item moved to trash")

@router.delete("/{id}/purge")
def purge_item(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Message:
    """
    Permanently delete an item.
    """
    item = session.get(Item, id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    session.delete(item)
    session.commit()
    return Message(message="Item permanently deleted")


@router.patch("/{id}", response_model=ItemPublic)
def update_item(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID, item_in: ItemUpdate
) -> Any:
    """
    Update an item by ID.
    """
    item = session.get(Item, id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Item is in trash")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")

    # Apply updates only if provided (partial update)
    if item_in.title is not None:
        item.title = item_in.title
    if item_in.description is not None:
        item.description = item_in.description

    session.add(item)
    session.commit()
    session.refresh(item)
    return item
