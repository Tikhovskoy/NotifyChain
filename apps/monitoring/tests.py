from django.test import TestCase
from django.contrib.auth.models import User
from .models import SystemMetrics, AlertRule


class SystemMetricsTest(TestCase):
    def test_metrics_creation(self):
        metrics = SystemMetrics.objects.create(
            notifications_sent=100, notifications_failed=5, email_sent=80, sms_sent=20
        )
        self.assertEqual(metrics.notifications_sent, 100)
        self.assertEqual(metrics.notifications_failed, 5)
        self.assertEqual(metrics.total_notifications, 105)

    def test_success_rate_calculation(self):
        metrics = SystemMetrics.objects.create(notifications_sent=95, notifications_failed=5)
        self.assertEqual(metrics.success_rate, 95.0)


class AlertRuleTest(TestCase):
    def test_alert_rule_creation(self):
        rule = AlertRule.objects.create(
            name="Низкий уровень успешности", metric="success_rate", condition="lt", threshold=90.0
        )
        self.assertEqual(rule.name, "Низкий уровень успешности")
        self.assertTrue(rule.check_condition(85.0))
        self.assertFalse(rule.check_condition(95.0))
