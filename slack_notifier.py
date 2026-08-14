import os
import requests
from datetime import datetime

class SlackNotifier:
    """Sends monitoring alerts to Slack.

    Slack is optional. With neither SLACK_WEBHOOK_URL nor a SLACK_TOKEN set,
    the notifier is disabled and every send returns False without making a
    request. Falling through to the Web API on an unset token sent
    ``Authorization: Bearer None`` to Slack and reported success on the 2xx
    error envelope Slack returns for it.
    """

    API_URL = 'https://slack.com/api/chat.postMessage'

    def __init__(self):
        self.webhook_url = os.getenv('SLACK_WEBHOOK_URL') or None
        self.token = os.getenv('SLACK_TOKEN') or None
        self.channel = os.getenv('SLACK_CHANNEL', '#db-monitoring')
        self.api_url = self.API_URL
        self.timeout = float(os.getenv('SLACK_TIMEOUT_SECONDS', 10))
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        }

    @property
    def enabled(self):
        """True when Slack is configured well enough to attempt a send."""
        return bool(self.webhook_url or (self.token and self.channel))

    def send_alert(self, alert_type, message, details=None, severity="info"):
        """Send an alert to Slack. Returns False if Slack is not configured."""
        if not self.enabled:
            return False

        emoji_map = {
            "critical": "🔴",
            "warning": "⚠️",
            "info": "ℹ️",
            "success": "✅"
        }
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emoji = emoji_map.get(severity.lower(), "ℹ️")
        
        if self.webhook_url:
            # Use webhook URL
            payload = {
                "text": f"{emoji} {alert_type}",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} {alert_type}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": message
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Time*: {current_time}"
                            }
                        ]
                    }
                ]
            }
            
            if details:
                payload["blocks"].insert(2, {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Details:*\n{details}"
                    }
                })
            
            try:
                response = requests.post(
                    self.webhook_url, json=payload, timeout=self.timeout
                )
                response.raise_for_status()
                return True
            except Exception as e:
                print(f"Failed to send Slack notification: {str(e)}")
                return False
        else:
            # Use Slack API
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {alert_type}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Time*: {current_time}"
                        }
                    ]
                }
            ]

            if details:
                blocks.insert(2, {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Details:*\n{details}"
                    }
                })

            payload = {
                "channel": self.channel,
                "blocks": blocks
            }

            try:
                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                # The Web API answers 200 with {"ok": false, "error": ...} for
                # a bad token or channel, so the status code alone is not an
                # outcome.
                body = response.json()
                if not body.get('ok'):
                    print(f"Slack rejected the message: {body.get('error')}")
                    return False
                return True
            except Exception as e:
                print(f"Failed to send Slack notification: {str(e)}")
                return False

    def send_query_alert(self, query_info):
        """Send query performance alert"""
        message = (
            f"*Database*: `{query_info['database']}`\n"
            f"*Slow Query Detected*\n```{query_info['query']}```"
        )
        details = (
            f"*Duration*: {query_info['duration']}ms\n"
            f"*Rows*: {query_info['rows']}\n"
            f"*Cache Hit Ratio*: {query_info['cache_hit_ratio']}%"
        )
        # Advice is optional: absent when no LLM key is configured.
        advice = query_info.get('advice')
        if advice:
            details += f"\n\n*Suggested tuning*\n{advice[:1500]}"
        return self.send_alert(
            "Query Performance Alert",
            message,
            details,
            "warning"
        )

    def send_connection_alert(self, connection_info):
        """Send connection usage alert"""
        message = (
            f"*Database*: `{connection_info['database']}`\n"
            "*High Connection Usage*"
        )
        details = (
            f"*Current Connections*: {connection_info['current']}\n"
            f"*Running Queries*: {connection_info['running']}\n"
            f"*Idle Connections*: {connection_info['idle']}\n"
            f"*Max Connections*: {connection_info['max']}\n"
            f"*Usage*: {connection_info['percentage']}%"
        )
        return self.send_alert(
            "Connection Alert",
            message,
            details,
            "warning"
        )

    def send_vacuum_alert(self, table_info):
        """Send vacuum requirement alert"""
        message = (
            f"*Database*: `{table_info['database']}`\n"
            f"*Table Requires VACUUM*: `{table_info['table']}`"
        )
        details = (
            f"*Dead Tuples*: {table_info['dead_tuples']}\n"
            f"*Live Tuples*: {table_info['live_tuples']}\n"
            f"*Dead Tuple Ratio*: {table_info['dead_ratio']}%\n"
            f"*Table Size*: {table_info['total_size']}\n"
            f"*Last Vacuum*: {table_info['last_vacuum']}\n"
            f"*Last Auto-vacuum*: {table_info['last_autovacuum']}"
        )
        return self.send_alert(
            "Maintenance Alert",
            message,
            details,
            "warning"
        )
