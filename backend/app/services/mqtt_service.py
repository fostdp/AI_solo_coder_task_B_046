import json
import logging
from typing import Optional, Dict, Any
import paho.mqtt.client as mqtt
from app.config import settings

logger = logging.getLogger(__name__)


class MQTTService:
    _instance: Optional['MQTTService'] = None
    _client: Optional[mqtt.Client] = None
    _connected: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._connected:
            self._init_client()

    def _init_client(self):
        try:
            self._client = mqtt.Client(client_id="water_heritage_backend", clean_session=True)
            if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
                self._client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_publish = self._on_publish

            try:
                self._client.connect_async(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60)
                self._client.loop_start()
            except Exception as e:
                logger.warning(f"MQTT连接失败(异步模式): {e}，告警将仅存储在数据库中")
                self._connected = False
        except Exception as e:
            logger.error(f"MQTT客户端初始化失败: {e}")
            self._connected = False

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            logger.info(f"MQTT已连接到 {settings.MQTT_HOST}:{settings.MQTT_PORT}")
        else:
            self._connected = False
            logger.error(f"MQTT连接失败，错误码: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            logger.warning(f"MQTT意外断开，错误码: {rc}")

    def _on_publish(self, client, userdata, mid):
        logger.debug(f"MQTT消息发布成功，消息ID: {mid}")

    def is_connected(self) -> bool:
        return self._connected

    def publish_alert(self, site_id: int, alert_data: Dict[str, Any]) -> bool:
        if not self._connected:
            logger.warning(f"MQTT未连接，告警无法推送: site_id={site_id}")
            return False

        topic = f"{settings.MQTT_TOPIC_PREFIX}/{site_id}"
        payload = json.dumps(alert_data, ensure_ascii=False, default=str)

        try:
            result = self._client.publish(
                topic,
                payload=payload,
                qos=1,
                retain=False
            )
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"告警已推送至MQTT主题 {topic}: {alert_data.get('message', '')[:50]}")
                return True
            else:
                logger.error(f"MQTT消息发布失败，错误码: {result.rc}")
                return False
        except Exception as e:
            logger.error(f"MQTT消息发布异常: {e}")
            return False

    def publish_custom(self, topic: str, message: Dict[str, Any], qos: int = 1) -> bool:
        if not self._connected:
            logger.warning(f"MQTT未连接，无法推送自定义消息")
            return False

        try:
            payload = json.dumps(message, ensure_ascii=False, default=str)
            result = self._client.publish(topic, payload=payload, qos=qos)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"MQTT自定义消息发布异常: {e}")
            return False

    def disconnect(self):
        if self._client and self._connected:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
            logger.info("MQTT已断开连接")
