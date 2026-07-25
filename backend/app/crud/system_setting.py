from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting


async def get_setting(db: AsyncSession, key: str) -> SystemSetting | None:
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    return result.scalar_one_or_none()


async def set_setting(db: AsyncSession, key: str, value: str, updated_by) -> SystemSetting:
    setting = await get_setting(db, key)
    if setting is None:
        setting = SystemSetting(key=key, value=value, updated_by=updated_by)
        db.add(setting)
    else:
        setting.value = value
        setting.updated_by = updated_by

    await db.commit()
    await db.refresh(setting)
    return setting
