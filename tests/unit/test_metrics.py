"""
Tests del módulo puro de métricas (app/metrics.py) - Ciclo 4, ciclo 1.

Tests obligatorios (rojo antes de implementar):
- Contador simple con valores y etiquetas.
- Histograma acumulativo correcto con buckets fijos (+Inf, _sum, _count).
- Escape de etiquetas (comillas, backslash, nueva línea).
- Render a texto formato Prometheus text/plain version=0.0.4.
"""

import pytest

from app.metrics import (
    MetricRegistry,
    render_text,
)


def test_contador_simple():
    reg = MetricRegistry()
    c = reg.counter("http_requests_total", ["method", "route", "status"])
    c.inc({"method": "GET", "route": "/api/v1/documents", "status": "200"})
    c.inc({"method": "GET", "route": "/api/v1/documents", "status": "200"})
    c.inc({"method": "POST", "route": "/api/v1/documents", "status": "201"})
    assert c.value({"method": "GET", "route": "/api/v1/documents", "status": "200"}) == 2
    assert c.value({"method": "POST", "route": "/api/v1/documents", "status": "201"}) == 1
    assert c.value({"method": "GET", "route": "/api/v1/documents", "status": "404"}) == 0


def test_contador_por_etiqueta_distinta_serie():
    reg = MetricRegistry()
    c = reg.counter("http_requests_total", ["method", "route", "status"])
    c.inc({"method": "GET", "route": "/api/v1/documents", "status": "200"})
    c.inc({"method": "GET", "route": "/api/v1/documents/{id}", "status": "200"})
    assert c.value({"method": "GET", "route": "/api/v1/documents", "status": "200"}) == 1
    assert c.value({"method": "GET", "route": "/api/v1/documents/{id}", "status": "200"}) == 1


def test_histograma_acumulativo_correcto():
    reg = MetricRegistry()
    buckets = (0.005, 0.01, 0.025, 0.05, 1.0, float("inf"))
    h = reg.histogram("http_request_duration_seconds", ["method", "route"], buckets=buckets)
    h.observe(0.003, {"method": "GET", "route": "/trace"})
    h.observe(0.007, {"method": "GET", "route": "/trace"})
    h.observe(0.03, {"method": "GET", "route": "/trace"})
    h.observe(2.0, {"method": "GET", "route": "/trace"})

    # +Inf acumula todas las observaciones (4)
    assert h.count({"method": "GET", "route": "/trace"}) == 4
    assert h.sum({"method": "GET", "route": "/trace"}) == pytest.approx(2.04)


def test_histograma_buckets_le():
    reg = MetricRegistry()
    buckets = (0.005, 0.01, float("inf"))
    h = reg.histogram("http_request_duration_seconds", ["method", "route"], buckets=buckets)
    h.observe(0.003, {"method": "GET", "route": "/health/live"})
    h.observe(0.007, {"method": "GET", "route": "/health/live"})
    h.observe(0.5, {"method": "GET", "route": "/health/live"})

    assert h.bucket_count(0.005, {"method": "GET", "route": "/health/live"}) == 1
    assert h.bucket_count(0.01, {"method": "GET", "route": "/health/live"}) == 2
    assert h.bucket_count(float("inf"), {"method": "GET", "route": "/health/live"}) == 3
    # +Inf debe acumular todas las observaciones: +Inf == _count
    assert h.bucket_count(
        float("inf"), {"method": "GET", "route": "/health/live"}
    ) == h.count({"method": "GET", "route": "/health/live"})


def test_escape_etiquetas():
    reg = MetricRegistry()
    c = reg.counter("test_counter", ["route"])
    # Comillas dobles, backslash y nueva línea deben escaparse
    c.inc({'route': 'a"b\\c\nd'})
    texto = render_text(reg)
    assert '\\"' in texto
    assert '\\\\' in texto
    assert '\\n' in texto


def test_gauge_valor_actual():
    reg = MetricRegistry()
    g = reg.gauge("mongodb_up")
    g.set(1, {})
    g.set(0, {})
    assert g.value({}) == 0


def test_render_texto_formato_prometheus():
    reg = MetricRegistry()
    c = reg.counter("http_requests_total", ["method", "route", "status"])
    c.inc({"method": "GET", "route": "/api/v1/documents", "status": "200"}, 3)
    c.inc({"method": "POST", "route": "/api/v1/documents", "status": "201"}, 2)

    buckets2 = (0.005, float("inf"))
    h = reg.histogram("http_request_duration_seconds", ["method", "route"], buckets=buckets2)
    h.observe(0.003, {"method": "GET", "route": "/health/live"})

    g = reg.gauge("mongodb_up")
    g.set(1, {})

    texto = render_text(reg)
    assert texto.startswith("# HELP http_requests_total\n# TYPE http_requests_total counter\n")
    assert 'http_requests_total{method="GET",route="/api/v1/documents",status="200"} 3.0' in texto
    assert 'http_requests_total{method="POST",route="/api/v1/documents",status="201"} 2.0' in texto
    assert (
        "# HELP http_request_duration_seconds\n"
        "# TYPE http_request_duration_seconds histogram\n"
    ) in texto
    assert (
        'http_request_duration_seconds_bucket{method="GET",route="/health/live",'
        'le="0.005"} 1.0'
    ) in texto
    assert (
        'http_request_duration_seconds_bucket{method="GET",route="/health/live",'
        'le="+Inf"} 1.0'
    ) in texto
    assert 'http_request_duration_seconds_count{method="GET",route="/health/live"} 1.0' in texto
    assert 'http_request_duration_seconds_sum{method="GET",route="/health/live"} 0.003' in texto
    assert "# HELP mongodb_up\n# TYPE mongodb_up gauge\n" in texto
    assert "mongodb_up 1.0" in texto


def test_render_texto_vacio_sin_metricas():
    reg = MetricRegistry()
    assert render_text(reg) == ""
