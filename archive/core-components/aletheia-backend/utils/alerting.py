"""
Aletheia Alerting Module

Provides alert management and notification capabilities for monitoring system health.
Supports multiple notification channels: DingTalk, WeChat Work, Email, Slack, Webhook.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiohttp

from utils.logging import logger
from core.config import settings


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status"""
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass
class Alert:
    """Alert data structure"""
    name: str
    severity: AlertSeverity
    status: AlertStatus
    message: str
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    starts_at: datetime = field(default_factory=datetime.now)
    ends_at: Optional[datetime] = None
    generator_url: Optional[str] = None
    fingerprint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "severity": self.severity.value,
            "status": self.status.value,
            "message": self.message,
            "labels": self.labels,
            "annotations": self.annotations,
            "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "generator_url": self.generator_url,
            "fingerprint": self.fingerprint,
        }


class NotificationChannel(ABC):
    """Abstract base class for notification channels"""

    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """Send alert notification"""
        pass

    @abstractmethod
    async def send_batch(self, alerts: List[Alert]) -> bool:
        """Send batch of alerts"""
        pass


class DingTalkChannel(NotificationChannel):
    """DingTalk notification channel"""

    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        self.webhook_url = webhook_url
        self.secret = secret

    def _sign(self, timestamp: str) -> str:
        """Generate DingTalk signature"""
        if not self.secret:
            return ""

        import hmac
        import hashlib
        import base64
        import urllib.parse

        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return sign

    async def send(self, alert: Alert) -> bool:
        """Send alert to DingTalk"""
        try:
            timestamp = str(int(time.time() * 1000))
            url = self.webhook_url
            if self.secret:
                sign = self._sign(timestamp)
                url = f"{url}&timestamp={timestamp}&sign={sign}"

            # Build message
            severity_emoji = {
                AlertSeverity.INFO: "ℹ️",
                AlertSeverity.WARNING: "⚠️",
                AlertSeverity.ERROR: "❌",
                AlertSeverity.CRITICAL: "🔥",
            }

            status_emoji = "🔥" if alert.status == AlertStatus.FIRING else "✅"

            title = f"{status_emoji} [{alert.severity.value.upper()}] {alert.name}"
            content = f"""
**Status**: {alert.status.value}
**Severity**: {alert.severity.value}
**Message**: {alert.message}
**Time**: {alert.starts_at.strftime('%Y-%m-%d %H:%M:%S')}
"""
            if alert.labels:
                content += "\n**Labels**:\n"
                for k, v in alert.labels.items():
                    content += f"- {k}: {v}\n"

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"### {title}\n{content}",
                },
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    result = await response.json()
                    if result.get("errcode") == 0:
                        logger.info(f"DingTalk alert sent: {alert.name}")
                        return True
                    else:
                        logger.error(f"DingTalk alert failed: {result}")
                        return False

        except Exception as e:
            logger.error(f"DingTalk notification error: {e}")
            return False

    async def send_batch(self, alerts: List[Alert]) -> bool:
        """Send batch of alerts (sends first alert only, DingTalk doesn't support batch)"""
        if not alerts:
            return True
        return await self.send(alerts[0])


class WeChatWorkChannel(NotificationChannel):
    """WeChat Work (企业微信) notification channel"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, alert: Alert) -> bool:
        """Send alert to WeChat Work"""
        try:
            severity_color = {
                AlertSeverity.INFO: "info",
                AlertSeverity.WARNING: "warning",
                AlertSeverity.ERROR: "warning",
                AlertSeverity.CRITICAL: "warning",
            }

            status_text = "告警" if alert.status == AlertStatus.FIRING else "恢复"

            content = f"""
**[{status_text}] {alert.name}**
> 级别: {alert.severity.value}
> 状态: {alert.status.value}
> 信息: {alert.message}
> 时间: {alert.starts_at.strftime('%Y-%m-%d %H:%M:%S')}
"""

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": content,
                },
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    result = await response.json()
                    if result.get("errcode") == 0:
                        logger.info(f"WeChat Work alert sent: {alert.name}")
                        return True
                    else:
                        logger.error(f"WeChat Work alert failed: {result}")
                        return False

        except Exception as e:
            logger.error(f"WeChat Work notification error: {e}")
            return False

    async def send_batch(self, alerts: List[Alert]) -> bool:
        """Send batch alerts"""
        if not alerts:
            return True
        return await self.send(alerts[0])


class SlackChannel(NotificationChannel):
    """Slack notification channel"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, alert: Alert) -> bool:
        """Send alert to Slack"""
        try:
            severity_color = {
                AlertSeverity.INFO: "#36a64f",
                AlertSeverity.WARNING: "#ff9900",
                AlertSeverity.ERROR: "#ff0000",
                AlertSeverity.CRITICAL: "#8b0000",
            }

            fields = [
                {"title": "Status", "value": alert.status.value, "short": True},
                {"title": "Severity", "value": alert.severity.value, "short": True},
                {"title": "Message", "value": alert.message, "short": False},
            ]

            if alert.labels:
                labels_text = ", ".join(f"{k}={v}" for k, v in alert.labels.items())
                fields.append({"title": "Labels", "value": labels_text, "short": False})

            payload = {
                "attachments": [
                    {
                        "color": severity_color.get(alert.severity, "#808080"),
                        "title": alert.name,
                        "fields": fields,
                        "footer": "Aletheia Alerting",
                        "ts": int(alert.starts_at.timestamp()),
                    }
                ]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        logger.info(f"Slack alert sent: {alert.name}")
                        return True
                    else:
                        text = await response.text()
                        logger.error(f"Slack alert failed: {text}")
                        return False

        except Exception as e:
            logger.error(f"Slack notification error: {e}")
            return False

    async def send_batch(self, alerts: List[Alert]) -> bool:
        """Send batch alerts"""
        if not alerts:
            return True

        try:
            attachments = []
            severity_color = {
                AlertSeverity.INFO: "#36a64f",
                AlertSeverity.WARNING: "#ff9900",
                AlertSeverity.ERROR: "#ff0000",
                AlertSeverity.CRITICAL: "#8b0000",
            }

            for alert in alerts[:10]:  # Slack limits to ~10 attachments
                attachments.append({
                    "color": severity_color.get(alert.severity, "#808080"),
                    "title": alert.name,
                    "text": alert.message,
                    "footer": alert.status.value,
                    "ts": int(alert.starts_at.timestamp()),
                })

            payload = {"attachments": attachments}

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200

        except Exception as e:
            logger.error(f"Slack batch notification error: {e}")
            return False


class EmailChannel(NotificationChannel):
    """Email notification channel"""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_addr: str,
        to_addrs: List[str],
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.use_tls = use_tls

    async def send(self, alert: Alert) -> bool:
        """Send alert via email"""
        try:
            subject = f"[{alert.severity.value.upper()}] {alert.name} - {alert.status.value}"

            body = f"""
Alert: {alert.name}
Status: {alert.status.value}
Severity: {alert.severity.value}
Message: {alert.message}
Time: {alert.starts_at.strftime('%Y-%m-%d %H:%M:%S')}

Labels:
{json.dumps(alert.labels, indent=2) if alert.labels else 'None'}

Annotations:
{json.dumps(alert.annotations, indent=2) if alert.annotations else 'None'}
"""

            msg = MIMEMultipart()
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(self.to_addrs)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            # Run in thread pool for synchronous SMTP operations
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._send_email_sync,
                msg,
            )

            logger.info(f"Email alert sent: {alert.name}")
            return True

        except Exception as e:
            logger.error(f"Email notification error: {e}")
            return False

    def _send_email_sync(self, msg: MIMEMultipart):
        """Synchronously send email"""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.use_tls:
                server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.from_addr, self.to_addrs, msg.as_string())

    async def send_batch(self, alerts: List[Alert]) -> bool:
        """Send batch alerts (combines into one email)"""
        if not alerts:
            return True

        try:
            subject = f"[ALERT BATCH] {len(alerts)} alerts"

            body_parts = ["Alert Summary:\n"]
            for i, alert in enumerate(alerts, 1):
                body_parts.append(
                    f"\n{i}. [{alert.severity.value}] {alert.name}: {alert.message}"
                )

            msg = MIMEMultipart()
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(self.to_addrs)
            msg["Subject"] = subject
            msg.attach(MIMEText("\n".join(body_parts), "plain"))

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._send_email_sync,
                msg,
            )

            return True

        except Exception as e:
            logger.error(f"Email batch notification error: {e}")
            return False


class WebhookChannel(NotificationChannel):
    """Generic webhook notification channel"""

    def __init__(self, webhook_url: str, headers: Optional[Dict[str, str]] = None):
        self.webhook_url = webhook_url
        self.headers = headers or {}

    async def send(self, alert: Alert) -> bool:
        """Send alert to webhook"""
        try:
            payload = alert.to_dict()

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status < 400:
                        logger.info(f"Webhook alert sent: {alert.name}")
                        return True
                    else:
                        text = await response.text()
                        logger.error(f"Webhook alert failed: {response.status} - {text}")
                        return False

        except Exception as e:
            logger.error(f"Webhook notification error: {e}")
            return False

    async def send_batch(self, alerts: List[Alert]) -> bool:
        """Send batch alerts"""
        if not alerts:
            return True

        try:
            payload = {"alerts": [a.to_dict() for a in alerts]}

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    return response.status < 400

        except Exception as e:
            logger.error(f"Webhook batch notification error: {e}")
            return False


class AlertRule:
    """Alert rule definition"""

    def __init__(
        self,
        name: str,
        condition: Callable[[], bool],
        severity: AlertSeverity = AlertSeverity.WARNING,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
        for_duration: int = 0,  # seconds before firing
        silence_duration: int = 300,  # seconds to silence after resolve
    ):
        self.name = name
        self.condition = condition
        self.severity = severity
        self.labels = labels or {}
        self.annotations = annotations or {}
        self.for_duration = for_duration
        self.silence_duration = silence_duration
        self._pending_since: Optional[datetime] = None
        self._firing_since: Optional[datetime] = None
        self._silenced_until: Optional[datetime] = None

    def evaluate(self) -> Optional[Alert]:
        """Evaluate the rule and return an alert if needed"""
        now = datetime.now()

        # Check if silenced
        if self._silenced_until and now < self._silenced_until:
            return None

        try:
            is_firing = self.condition()
        except Exception as e:
            logger.error(f"Alert rule '{self.name}' condition error: {e}")
            return None

        if is_firing:
            if self._firing_since:
                # Already firing
                return None

            if self._pending_since:
                # Pending
                if self.for_duration > 0:
                    elapsed = (now - self._pending_since).total_seconds()
                    if elapsed < self.for_duration:
                        return None

                # Transition to firing
                self._firing_since = now
                self._pending_since = None

                return Alert(
                    name=self.name,
                    severity=self.severity,
                    status=AlertStatus.FIRING,
                    message=self.annotations.get("summary", f"Alert {self.name} is firing"),
                    labels=self.labels,
                    annotations=self.annotations,
                    starts_at=now,
                )
            else:
                # Start pending
                self._pending_since = now
                return None
        else:
            # Not firing
            if self._firing_since:
                # Was firing, now resolved
                alert = Alert(
                    name=self.name,
                    severity=self.severity,
                    status=AlertStatus.RESOLVED,
                    message=self.annotations.get("summary", f"Alert {self.name} resolved"),
                    labels=self.labels,
                    annotations=self.annotations,
                    starts_at=self._firing_since,
                    ends_at=now,
                )
                self._firing_since = None
                self._pending_since = None
                self._silenced_until = now + timedelta(seconds=self.silence_duration)
                return alert

            # Reset pending
            self._pending_since = None
            return None


class AlertManager:
    """Central alert management"""

    def __init__(self):
        self._channels: List[NotificationChannel] = []
        self._rules: List[AlertRule] = []
        self._active_alerts: Dict[str, Alert] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._check_interval = 30  # seconds

    def add_channel(self, channel: NotificationChannel):
        """Add a notification channel"""
        self._channels.append(channel)

    def add_rule(self, rule: AlertRule):
        """Add an alert rule"""
        self._rules.append(rule)

    async def send_alert(self, alert: Alert):
        """Send alert to all channels"""
        if not self._channels:
            logger.warning(f"No notification channels configured for alert: {alert.name}")
            return

        # Update active alerts
        if alert.status == AlertStatus.FIRING:
            self._active_alerts[alert.name] = alert
        elif alert.name in self._active_alerts:
            del self._active_alerts[alert.name]

        # Send to all channels
        tasks = [channel.send(alert) for channel in self._channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Channel {i} send error: {result}")

    async def _evaluate_rules(self):
        """Evaluate all rules periodically"""
        for rule in self._rules:
            try:
                alert = rule.evaluate()
                if alert:
                    await self.send_alert(alert)
            except Exception as e:
                logger.error(f"Error evaluating rule '{rule.name}': {e}")

    async def _run_loop(self):
        """Main evaluation loop"""
        while self._running:
            try:
                await self._evaluate_rules()
            except Exception as e:
                logger.error(f"Alert evaluation error: {e}")

            await asyncio.sleep(self._check_interval)

    async def start(self):
        """Start alert manager"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Alert manager started")

    async def stop(self):
        """Stop alert manager"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Alert manager stopped")

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get list of active alerts"""
        return [a.to_dict() for a in self._active_alerts.values()]

    def get_rules(self) -> List[Dict[str, Any]]:
        """Get list of rules"""
        return [
            {
                "name": r.name,
                "severity": r.severity.value,
                "labels": r.labels,
                "annotations": r.annotations,
                "for_duration": r.for_duration,
            }
            for r in self._rules
        ]


# Global alert manager instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get the global alert manager instance"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


def setup_default_channels():
    """Setup default notification channels from settings"""
    manager = get_alert_manager()

    # DingTalk
    dingtalk_webhook = getattr(settings, 'ALERT_DINGTALK_WEBHOOK', None)
    if dingtalk_webhook:
        dingtalk_secret = getattr(settings, 'ALERT_DINGTALK_SECRET', None)
        manager.add_channel(DingTalkChannel(dingtalk_webhook, dingtalk_secret))

    # WeChat Work
    wechat_webhook = getattr(settings, 'ALERT_WECHAT_WEBHOOK', None)
    if wechat_webhook:
        manager.add_channel(WeChatWorkChannel(wechat_webhook))

    # Slack
    slack_webhook = getattr(settings, 'ALERT_SLACK_WEBHOOK', None)
    if slack_webhook:
        manager.add_channel(SlackChannel(slack_webhook))

    # Email
    smtp_host = getattr(settings, 'ALERT_SMTP_HOST', None)
    if smtp_host:
        manager.add_channel(EmailChannel(
            smtp_host=smtp_host,
            smtp_port=getattr(settings, 'ALERT_SMTP_PORT', 587),
            smtp_user=getattr(settings, 'ALERT_SMTP_USER', ''),
            smtp_password=getattr(settings, 'ALERT_SMTP_PASSWORD', ''),
            from_addr=getattr(settings, 'ALERT_SMTP_FROM', 'alerts@aletheia.local'),
            to_addrs=getattr(settings, 'ALERT_SMTP_TO', []).split(',') if isinstance(getattr(settings, 'ALERT_SMTP_TO', ''), str) else getattr(settings, 'ALERT_SMTP_TO', []),
        ))

    # Generic Webhook
    webhook_url = getattr(settings, 'ALERT_WEBHOOK_URL', None)
    if webhook_url:
        webhook_headers = getattr(settings, 'ALERT_WEBHOOK_HEADERS', {})
        manager.add_channel(WebhookChannel(webhook_url, webhook_headers))


def setup_default_rules():
    """Setup default alert rules"""
    manager = get_alert_manager()

    # Circuit breaker open rule
    from utils.stability import get_circuit_breaker_registry

    def check_circuit_breaker_open() -> bool:
        registry = get_circuit_breaker_registry()
        for name, cb in registry.get_all().items():
            if cb.is_open:
                return True
        return False

    manager.add_rule(AlertRule(
        name="CircuitBreakerOpen",
        condition=check_circuit_breaker_open,
        severity=AlertSeverity.ERROR,
        labels={"component": "stability"},
        annotations={"summary": "Circuit breaker is open"},
        for_duration=30,
    ))

    # LLM provider unavailable rule
    def check_llm_unavailable() -> bool:
        try:
            from services.llm.llm_failover import get_global_failover_manager
            manager = get_global_failover_manager()
            status = manager.get_status()
            return status.get("available_providers", 0) == 0
        except Exception:
            return False

    manager.add_rule(AlertRule(
        name="LLMProvidersUnavailable",
        condition=check_llm_unavailable,
        severity=AlertSeverity.CRITICAL,
        labels={"component": "llm"},
        annotations={"summary": "All LLM providers are unavailable"},
        for_duration=60,
    ))

    # High error rate rule
    _error_count = 0
    _error_window_start = time.time()

    def check_high_error_rate() -> bool:
        nonlocal _error_count, _error_window_start
        from utils.metrics import errors_total

        try:
            # This is a simplified check - in production, you'd use Prometheus queries
            current_count = errors_total._value.get() if hasattr(errors_total, '_value') else 0
            now = time.time()

            if now - _error_window_start > 60:
                _error_count = current_count
                _error_window_start = now
                return False

            rate = (current_count - _error_count) / (now - _error_window_start)
            return rate > 10  # More than 10 errors per minute
        except Exception:
            return False

    manager.add_rule(AlertRule(
        name="HighErrorRate",
        condition=check_high_error_rate,
        severity=AlertSeverity.WARNING,
        labels={"component": "system"},
        annotations={"summary": "High error rate detected"},
        for_duration=60,
    ))


# Convenience functions
async def send_alert(
    name: str,
    severity: Union[AlertSeverity, str],
    message: str,
    labels: Optional[Dict[str, str]] = None,
):
    """Send a manual alert"""
    if isinstance(severity, str):
        severity = AlertSeverity(severity)

    alert = Alert(
        name=name,
        severity=severity,
        status=AlertStatus.FIRING,
        message=message,
        labels=labels or {},
    )
    await get_alert_manager().send_alert(alert)


async def resolve_alert(name: str, message: str = ""):
    """Resolve an active alert"""
    manager = get_alert_manager()
    if name in manager._active_alerts:
        alert = manager._active_alerts[name]
        resolved = Alert(
            name=name,
            severity=alert.severity,
            status=AlertStatus.RESOLVED,
            message=message or f"Alert {name} resolved",
            labels=alert.labels,
            starts_at=alert.starts_at,
            ends_at=datetime.now(),
        )
        await manager.send_alert(resolved)