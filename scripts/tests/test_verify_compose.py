from unittest import TestCase

from scripts.verify_compose import validate


CONTROL_NETWORK = "control-plane"
USER_NETWORK = "streamlit-limited"


def minimal_model() -> dict:
    """A rendered Compose model with the required isolated service layout."""
    return {
        "services": {
            "traefik": {
                "image": "traefik:v3.6",
                "networks": {CONTROL_NETWORK: None, USER_NETWORK: None},
                "volumes": [
                    {
                        "source": "/var/run/docker.sock",
                        "target": "/var/run/docker.sock",
                        "read_only": True,
                    }
                ],
                "ports": [{"host_ip": "127.0.0.1", "target": 3001, "published": "3001"}],
            },
            "db": {"image": "postgres:16-alpine", "networks": {CONTROL_NETWORK: None}},
            "redis": {"image": "redis:7-alpine", "networks": {CONTROL_NETWORK: None}},
            "keycloak": {
                "image": "quay.io/keycloak/keycloak:25.0",
                "networks": {CONTROL_NETWORK: None},
            },
            "backend": {"image": "sthub-backend", "networks": {CONTROL_NETWORK: None}},
            "worker": {
                "image": "sthub-worker",
                "networks": {CONTROL_NETWORK: None},
                "volumes": [
                    {
                        "source": "/var/run/docker.sock",
                        "target": "/var/run/docker.sock",
                        "read_only": False,
                    }
                ],
            },
            "frontend": {"image": "sthub-frontend", "networks": {CONTROL_NETWORK: None}},
        }
    }


class ComposeBoundaryTests(TestCase):
    def test_accepts_isolated_static_services_and_socket_modes(self):
        self.assertEqual(validate(minimal_model(), tls=False), [])

    def test_rejects_backend_on_user_network(self):
        model = minimal_model()
        model["services"]["backend"]["networks"][USER_NETWORK] = None

        self.assertIn("backend must not join the user-app network", validate(model, tls=False))

    def test_rejects_socket_on_backend(self):
        model = minimal_model()
        model["services"]["backend"]["volumes"] = [
            {"source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}
        ]

        self.assertIn("backend must not mount the Docker socket", validate(model, tls=False))

    def test_rejects_incorrect_socket_access_modes(self):
        model = minimal_model()
        model["services"]["worker"]["volumes"][0]["read_only"] = True
        model["services"]["traefik"]["volumes"][0]["read_only"] = False

        self.assertEqual(
            validate(model, tls=False),
            [
                "traefik Docker socket mount must be read-only",
                "worker Docker socket mount must be read-write",
            ],
        )

    def test_rejects_missing_required_service(self):
        model = minimal_model()
        del model["services"]["redis"]

        self.assertEqual(validate(model, tls=False), ["missing required service: redis"])

    def test_rejects_non_443_tls_port(self):
        model = minimal_model()
        model["services"]["traefik"]["ports"] = [
            {"target": 443, "published": "443"},
            {"target": 8080, "published": "8080"},
        ]

        self.assertEqual(validate(model, tls=True), ["TLS stack must publish only port 443"])

    def test_rejects_a_static_service_published_in_tls_mode(self):
        model = minimal_model()
        model["services"]["traefik"]["ports"] = [{"target": 443, "published": "443"}]
        model["services"]["backend"]["ports"] = [{"target": 8000, "published": "8000"}]

        self.assertEqual(
            validate(model, tls=True),
            [
                "TLS stack must publish only port 443",
                "backend must not publish a host port in the TLS stack",
            ],
        )

    def test_rejects_backend_publishing_tls_port_443(self):
        model = minimal_model()
        model["services"]["traefik"]["ports"] = [{"target": 443, "published": "443"}]
        model["services"]["backend"]["ports"] = [{"target": 443, "published": "443"}]

        self.assertEqual(
            validate(model, tls=True),
            ["backend must not publish a host port in the TLS stack"],
        )

    def test_rejects_unlisted_service_on_user_network(self):
        model = minimal_model()
        model["services"]["metrics"] = {"networks": {CONTROL_NETWORK: None, USER_NETWORK: None}}

        self.assertIn("metrics must not join the user-app network", validate(model, tls=False))

    def test_rejects_host_wide_port_publication_in_the_http_stack(self):
        """Dropping the 127.0.0.1 prefix would expose the HTTP stack to the network."""
        model = minimal_model()
        model["services"]["traefik"]["ports"] = [{"target": 3001, "published": "3001"}]

        self.assertEqual(
            validate(model, tls=False),
            ["traefik must publish port 3001 on loopback only in the HTTP stack"],
        )

    def test_rejects_host_wide_short_syntax_port(self):
        """The short `3001:3001` form binds every interface just as silently."""
        model = minimal_model()
        model["services"]["traefik"]["ports"] = ["3001:3001"]

        self.assertEqual(
            validate(model, tls=False),
            ["traefik must publish port 3001 on loopback only in the HTTP stack"],
        )

    def test_accepts_loopback_short_syntax_port(self):
        model = minimal_model()
        model["services"]["traefik"]["ports"] = ["127.0.0.1:3001:3001"]

        self.assertEqual(validate(model, tls=False), [])

    def test_rejects_private_registry_image(self):
        model = minimal_model()
        model["services"]["frontend"]["image"] = "registry.example.internal/frontend:latest"

        self.assertEqual(
            validate(model, tls=False),
            ["frontend must not use a private registry image reference"],
        )
