// Certificat PUBLIC de la CA interne SENTINEL-X (copie de docker/mosquitto/certs/ca.crt).
// Ce n'est pas un secret : il sert seulement à VÉRIFIER l'identité du broker.
// À régénérer uniquement si la CA elle-même est refaite (pas quand l'IP du broker change).
#pragma once

static const char CA_CERT[] = R"PEM(
-----BEGIN CERTIFICATE-----
MIIDDzCCAfegAwIBAgIUFr/BrhteGdAd7yNPd/nYQhdo9s8wDQYJKoZIhvcNAQEL
BQAwFzEVMBMGA1UEAwwMU2VudGluZWxYLUNBMB4XDTI2MTAwNTA4MDkzOVoXDTI3
MTAwNTA4MDkzOVowFzEVMBMGA1UEAwwMU2VudGluZWxYLUNBMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvXKv8cPLZOw0ExoHZ2NLNYp+DRhRP0+ja0xT
3uM1TW7NVDoZ9Ug3t4lJyYtmjquNqawZDgeq9JuB2SOQVqZkxcFeVwdbN7WbmbVx
7L7HUUt7v1wOzcRg0X+wa2TAt/v+iGLRvvHx95PbK1d88UWhz11fRPTGjvLRdCDe
1GKoxu8jRb1OaU0AgiaUuKllA/BbeAIF+jdmqAPPj64miEkiONDq+lWrfkeKirKp
sOozoSFvnRec/LymyiHzY8gT+1OkFpeCzhRrYGPyeaYEE/rLY0mrJIMWiSa8eDeT
4fHQ6r3j66UG+xqxjogLeMeenQTx3BcKn9Sp9vcuRjFg7IZtVwIDAQABo1MwUTAd
BgNVHQ4EFgQUcA9dlT+/Yf997R3RYcT983E2PD4wHwYDVR0jBBgwFoAUcA9dlT+/
Yf997R3RYcT983E2PD4wDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOC
AQEAXHgkS4vyL5KantZBnVYnxXJknFlm+Cage70HIH6rvcVPii2rKztGnRvkWvLp
nfHG8Fw2c08XDp8F6OxHjzV3rBuOIfB07xPMuhRV+qVTmX7a/V4Njvj+8RsS1E4H
60QLYVHBrBA9MdUgGlLfVuzLG4rf2kEgtVFxFBxFXAnXrZHXVJMJZ7wFLtAewbTH
TeERRCjtt4As91tRR+bwJNVyqoFOr0kUSy0Kkr7YaWka/LUnMZXjK9bMfX/MBcVF
N6RU2OWUuttsnmiKwACog5SOd3XYmLahy4W4z9R3n66QITASI4jkuDRL9QBmcHHI
psAUn1qTej6HIquPwNpb2l22rg==
-----END CERTIFICATE-----
)PEM";
