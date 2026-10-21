per_listener_settings false
persistence true
persistence_location /mosquitto/data/
log_dest stdout

plugin /usr/lib/mosquitto_dynamic_security.so
plugin_opt_config_file /mosquitto/data/dynamic-security.json

# internal (docker network only, not published) - used by the backend
listener 1883 0.0.0.0

# external TLS listener for PLC gateways; certificate obtained by Caddy for the domain
listener 8883 0.0.0.0
certfile /mosquitto/certs/server.crt
keyfile /mosquitto/certs/server.key
