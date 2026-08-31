from sqlalchemy.orm import Session

from app.models.external_integration import ExternalIntegration


def get_integration(
    db: Session,
    user_id: int,
    provider: str,
):
    return (
        db.query(ExternalIntegration)
        .filter(
            ExternalIntegration.user_id == user_id,
            ExternalIntegration.provider == provider,
        )
        .first()
    )


def create_integration(
    db: Session,
    integration: ExternalIntegration,
):
    db.add(integration)
    db.commit()
    db.refresh(integration)

    return integration


def update_integration(
    db: Session,
    integration: ExternalIntegration,
):
    db.add(integration)
    db.commit()
    db.refresh(integration)

    return integration


def delete_integration(
    db: Session,
    integration: ExternalIntegration,
):
    db.delete(integration)
    db.commit()
