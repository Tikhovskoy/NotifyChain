import logging
from celery import shared_task
from django.utils import timezone
from typing import Dict, Any, List

from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.notifications.utils import NotificationHelper
from apps.providers.services import ProviderManager
from apps.monitoring.models import PerformanceLog

logger = logging.getLogger("notifychain.tasks")


@shared_task(bind=True, max_retries=3)
def send_notification_task(self, notification_id: int) -> Dict[str, Any]:
    start_time = timezone.now()

    try:
        notification = Notification.objects.get(id=notification_id)

        if not notification.is_ready_to_send():
            logger.warning(f"Уведомление {notification_id} не готово к отправке")
            return {
                "success": False,
                "notification_id": notification_id,
                "error": "Notification is not ready to send",
            }

        notification_service = NotificationService()
        success = notification_service.send_notification(notification)

        duration = (timezone.now() - start_time).total_seconds()

        PerformanceLog.objects.create(
            operation="send_notification",
            duration=duration,
            channel=notification.channel,
            success=success,
            error_message=notification.error_message if not success else "",
            metadata={
                "notification_id": notification_id,
                "channel": notification.channel,
                "retry_count": notification.retry_count,
            },
        )

        result = {
            "success": success,
            "notification_id": notification_id,
            "status": notification.status,
            "duration": duration,
        }

        if success:
            logger.info(f"Успешно отправлено уведомление {notification_id} за {duration:.3f}с")
        else:
            logger.error(
                f"Ошибка отправки уведомления {notification_id}: {notification.error_message}"
            )

            if notification.can_retry():
                countdown = min(60 * (2**notification.retry_count), 3600)
                logger.info(
                    f"Повтор отправки уведомления {notification_id} через {countdown} секунд"
                )

                raise self.retry(
                    countdown=countdown,
                    exc=Exception(f"Ошибка отправки уведомления: {notification.error_message}"),
                )

        return result

    except Notification.DoesNotExist:
        error_msg = f"Уведомление {notification_id} не найдено"
        logger.error(error_msg)
        return {"success": False, "notification_id": notification_id, "error": error_msg}

    except Exception as exc:
        duration = (timezone.now() - start_time).total_seconds()

        PerformanceLog.objects.create(
            operation="send_notification",
            duration=duration,
            success=False,
            error_message=str(exc),
            metadata={"notification_id": notification_id},
        )

        logger.error(f"Ошибка в задаче отправки {notification_id}: {str(exc)}")

        if self.request.retries < self.max_retries:
            countdown = min(60 * (2**self.request.retries), 3600)
            logger.info(f"Повтор задачи для уведомления {notification_id} через {countdown} секунд")
            raise self.retry(countdown=countdown, exc=exc)

        return {
            "success": False,
            "notification_id": notification_id,
            "error": str(exc),
            "retries_exhausted": True,
        }


@shared_task
def send_bulk_notifications_task(notification_ids: List[int]) -> Dict[str, Any]:
    start_time = timezone.now()
    results = []

    logger.info(f"Начало массовой отправки {len(notification_ids)} уведомлений")

    for notification_id in notification_ids:
        send_notification_task.delay(notification_id)
        results.append({"notification_id": notification_id, "queued": True})

    duration = (timezone.now() - start_time).total_seconds()

    PerformanceLog.objects.create(
        operation="bulk_send_notifications",
        duration=duration,
        success=True,
        metadata={
            "notification_count": len(notification_ids),
            "notification_ids": notification_ids,
        },
    )

    logger.info(
        f"{len(notification_ids)} уведомлений поставлено в очередь на отправку за {duration:.3f}с"
    )

    return {
        "success": True,
        "queued_count": len(notification_ids),
        "results": results,
        "duration": duration,
    }


@shared_task
def process_scheduled_notifications() -> Dict[str, Any]:
    start_time = timezone.now()

    scheduled_notifications = Notification.objects.filter(
        status="pending", scheduled_at__isnull=False, scheduled_at__lte=timezone.now()
    )

    count = 0
    for notification in scheduled_notifications:
        send_notification_task.delay(notification.id)
        count += 1

    duration = (timezone.now() - start_time).total_seconds()

    logger.info(f"{count} запланированных уведомлений поставлено в очередь за {duration:.3f}с")

    return {"success": True, "processed_count": count, "duration": duration}


@shared_task
def retry_failed_notifications() -> Dict[str, Any]:
    start_time = timezone.now()

    failed_notifications = NotificationHelper.get_failed_notifications_for_retry(100)

    count = 0
    for notification in failed_notifications:
        if notification.can_retry():
            send_notification_task.delay(notification.id)
            count += 1

    duration = (timezone.now() - start_time).total_seconds()

    logger.info(f"{count} неудачных уведомлений поставлено на повтор за {duration:.3f}с")

    return {"success": True, "retry_count": count, "duration": duration}


@shared_task
def cleanup_old_notifications() -> Dict[str, Any]:
    start_time = timezone.now()

    deleted_count = NotificationHelper.cleanup_old_notifications(days=90)

    duration = (timezone.now() - start_time).total_seconds()

    logger.info(f"Удалено {deleted_count} старых уведомлений за {duration:.3f}с")

    return {"success": True, "deleted_count": deleted_count, "duration": duration}


@shared_task
def collect_system_metrics() -> Dict[str, Any]:
    from apps.monitoring.models import SystemMetrics
    from django.db.models import Count

    start_time = timezone.now()

    hour_ago = timezone.now() - timezone.timedelta(hours=1)

    notifications_last_hour = Notification.objects.filter(created_at__gte=hour_ago)

    status_counts = dict(
        notifications_last_hour.values("status")
        .annotate(count=Count("id"))
        .values_list("status", "count")
    )

    channel_counts = dict(
        notifications_last_hour.values("channel")
        .annotate(count=Count("id"))
        .values_list("channel", "count")
    )

    metrics = SystemMetrics.objects.create(
        notifications_sent=status_counts.get("sent", 0) + status_counts.get("delivered", 0),
        notifications_failed=status_counts.get("failed", 0),
        notifications_queued=status_counts.get("pending", 0) + status_counts.get("queued", 0),
        email_sent=channel_counts.get("email", 0),
        sms_sent=channel_counts.get("sms", 0),
        push_sent=channel_counts.get("push", 0),
        active_users=0,
        queue_size=Notification.objects.filter(status__in=["pending", "queued"]).count(),
    )

    duration = (timezone.now() - start_time).total_seconds()

    logger.info(f"Собраны системные метрики за {duration:.3f}с")

    return {
        "success": True,
        "metrics_id": metrics.id,
        "duration": duration,
        "total_notifications": metrics.total_notifications,
        "success_rate": metrics.success_rate,
    }


@shared_task
def test_provider_connectivity() -> Dict[str, Any]:
    from apps.providers.models import Provider

    start_time = timezone.now()
    provider_manager = ProviderManager()

    results = []
    active_providers = Provider.objects.filter(is_active=True)

    for provider in active_providers:
        try:
            test_result = provider_manager.test_provider(provider.id)
            results.append(
                {
                    "provider_id": provider.id,
                    "provider_name": provider.name,
                    "test_passed": test_result.get("connection_test", False),
                    "errors": test_result.get("errors", []),
                }
            )
        except Exception as e:
            results.append(
                {
                    "provider_id": provider.id,
                    "provider_name": provider.name,
                    "test_passed": False,
                    "errors": [str(e)],
                }
            )

    duration = (timezone.now() - start_time).total_seconds()

    successful_tests = len([r for r in results if r["test_passed"]])

    logger.info(
        f"Проверено {len(results)} провайдеров, {successful_tests} успешно за {duration:.3f}с"
    )

    return {
        "success": True,
        "tested_count": len(results),
        "successful_count": successful_tests,
        "results": results,
        "duration": duration,
    }
