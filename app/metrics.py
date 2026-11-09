"""
Módulo puro de métricas en formato Prometheus (text/plain; version=0.0.4).

Sin dependencias de FastAPI ni de prometheus_client: todo escrito a mano para
poder reutilizarlo tanto en el middleware de métricas como en los tests.

Contadores e histogramas son acumulativos por proceso (memoria).
"""

from __future__ import annotations

import math
from typing import Any, Dict


def _escape_label(value: str) -> str:
    """Escapa una etiqueta para el formato de texto de Prometheus.

    Reglas: backslash -> \\, comilla doble -> \", nueva línea -> \n.
    Devuelve una cadena nueva (no muta).
    """
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_label_value(value: str) -> str:
    return f'"{_escape_label(value)}"'


def _format_labels(labels: Dict[str, str]) -> str:
    if not labels:
        return ""
    partes = [f'{k}={_format_label_value(v)}' for k, v in labels.items()]
    return "{" + ",".join(partes) + "}"


class Counter:
    """Contador acumulativo con etiquetas."""

    def __init__(self, name: str, labelnames: tuple[str, ...]) -> None:
        self.name = name
        self.labelnames = labelnames
        self._values: Dict[tuple[Any, ...], float] = {}

    def _key(self, labels: Dict[str, str]) -> tuple[Any, ...]:
        return tuple(labels.get(ln, "") for ln in self.labelnames)

    def inc(self, labels: Dict[str, str], amount: float = 1.0) -> None:
        key = self._key(labels)
        self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, labels: Dict[str, str]) -> float:
        return self._values.get(self._key(labels), 0.0)

    def items(self) -> list[tuple[Dict[str, str], float]]:
        return [
            (
                dict(zip(self.labelnames, key, strict=False)),
                val,
            )
            for key, val in self._values.items()
        ]


class Histogram:
    """Histograma acumulativo con buckets fijos.

    Rastrea conteo acumulado por bucket (_bucket), conteo total (_count) y
    suma de valores (_sum).
    """

    def __init__(
        self,
        name: str,
        labelnames: tuple[str, ...],
        buckets: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, float("inf")),
    ) -> None:
        self.name = name
        self.labelnames = labelnames
        self.buckets = tuple(buckets)
        self._bucket_counts: Dict[tuple[Any, ...], list[int]] = {}
        self._counts: Dict[tuple[Any, ...], int] = {}
        self._sums: Dict[tuple[Any, ...], float] = {}

    def _key(self, labels: Dict[str, str]) -> tuple[Any, ...]:
        return tuple(labels.get(ln, "") for ln in self.labelnames)

    def observe(self, value: float, labels: Dict[str, str]) -> None:
        key = self._key(labels)
        if key not in self._bucket_counts:
            self._bucket_counts[key] = [0] * len(self.buckets)
            self._counts[key] = 0
            self._sums[key] = 0.0
        self._counts[key] += 1
        self._sums[key] += value
        for i, bucket in enumerate(self.buckets):
            if value <= bucket:
                self._bucket_counts[key][i] += 1

    def bucket_count(self, le: float, labels: Dict[str, str]) -> int:
        idx = self._bucket_index(le)
        return self._bucket_counts.get(self._key(labels), [0] * len(self.buckets))[idx]

    def count(self, labels: Dict[str, str]) -> int:
        return self._counts.get(self._key(labels), 0)

    def sum(self, labels: Dict[str, str]) -> float:
        return self._sums.get(self._key(labels), 0.0)

    def _bucket_index(self, le: float) -> int:
        for i, bucket in enumerate(self.buckets):
            if le == bucket:
                return i
        raise KeyError(f"bucket le={le} no está definido")

    def items(self) -> list[tuple[Dict[str, str], dict]]:
        resultado = []
        for key in self._counts:
            labels = dict(zip(self.labelnames, key, strict=False))
            resultado.append(
                (
                    labels,
                    {
                        "buckets": list(self._bucket_counts[key]),
                        "count": self._counts[key],
                        "sum": self._sums[key],
                    },
                )
            )
        return resultado


class Gauge:
    """Gauge: valor actual (no acumulativo)."""

    def __init__(self, name: str, labelnames: tuple[str, ...] = ()) -> None:
        self.name = name
        self.labelnames = labelnames
        self._values: Dict[tuple[Any, ...], float] = {}

    def _key(self, labels: Dict[str, str]) -> tuple[Any, ...]:
        return tuple(labels.get(ln, "") for ln in self.labelnames)

    def set(self, value: float, labels: Dict[str, str]) -> None:
        self._values[self._key(labels)] = float(value)

    def value(self, labels: Dict[str, str]) -> float:
        return self._values.get(self._key(labels), 0.0)

    def items(self) -> list[tuple[Dict[str, str], float]]:
        return [
            (
                dict(zip(self.labelnames, key, strict=False)),
                val,
            )
            for key, val in self._values.items()
        ]


class MetricRegistry:
    """Registro de métricas por nombre."""

    def __init__(self) -> None:
        self._counters: Dict[str, Counter] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._gauges: Dict[str, Gauge] = {}

    def counter(self, name: str, labelnames: tuple[str, ...] = ()) -> Counter:
        if name in self._counters:
            return self._counters[name]
        c = Counter(name, labelnames)
        self._counters[name] = c
        return c

    def histogram(
        self,
        name: str,
        labelnames: tuple[str, ...] = (),
        buckets: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, float("inf")),
    ) -> Histogram:
        if name in self._histograms:
            return self._histograms[name]
        h = Histogram(name, labelnames, buckets)
        self._histograms[name] = h
        return h

    def gauge(
        self, name: str, labelnames: tuple[str, ...] = ()
    ) -> Gauge:
        if name in self._gauges:
            return self._gauges[name]
        g = Gauge(name, labelnames)
        self._gauges[name] = g
        return g

    def counters(self) -> Dict[str, Counter]:
        return self._counters

    def histograms(self) -> Dict[str, Histogram]:
        return self._histograms

    def gauges(self) -> Dict[str, Gauge]:
        return self._gauges


def render_text(reg: MetricRegistry) -> str:
    """Renderiza el registro al formato de texto de Prometheus (0.0.4)."""

    lineas: list[str] = []

    for nombre, contador in reg.counters().items():
        lineas.append(f"# HELP {nombre}")
        lineas.append(f"# TYPE {nombre} counter")
        for etiquetas, valor in contador.items():
            lineas.append(
                f"{nombre}{_format_labels(etiquetas)} {repr(float(valor))}"
            )

    for nombre, histograma in reg.histograms().items():
        lineas.append(f"# HELP {nombre}")
        lineas.append(f"# TYPE {nombre} histogram")
        for etiquetas, datos in histograma.items():
            base = f"{nombre}_bucket"
            for i, bucket in enumerate(histograma.buckets):
                le_str = "+Inf" if math.isinf(bucket) else f"{bucket:g}"
                etiquetas_con_le = {**etiquetas, "le": le_str}
                lineas.append(
                    f"{base}{_format_labels(etiquetas_con_le)} {repr(float(datos['buckets'][i]))}"
                )
            lineas.append(
                f"{nombre}_count{_format_labels(etiquetas)} {repr(float(datos['count']))}"
            )
            lineas.append(
                f"{nombre}_sum{_format_labels(etiquetas)} {repr(float(datos['sum']))}"
            )

    for nombre, gauge in reg.gauges().items():
        lineas.append(f"# HELP {nombre}")
        lineas.append(f"# TYPE {nombre} gauge")
        for etiquetas, valor in gauge.items():
            lineas.append(f"{nombre}{_format_labels(etiquetas)} {repr(float(valor))}")

    if not lineas:
        return ""
    return "\n".join(lineas) + "\n"
