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
# minimum TLS 1.2 (TLS 1.3 also accepted); TLS 1.2 ciphers for RSA certificate, incl. non-PFS for embedded PLC stacks
tls_version tlsv1.2
ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA384:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256
