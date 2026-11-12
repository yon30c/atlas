# ADR-0001: Fundamentos del proyecto

- Estado: aceptado para Etapa 0
- Fecha: 2026-11-12

## Contexto

Atlas necesita un núcleo modular con límites de seguridad explícitos y sin acoplar la etapa fundacional a infraestructura.

## Decisiones

1. Organizar el núcleo en paquetes Python por responsabilidad.
2. Hacer de `MemoryGateway` la única frontera de acceso a memoria; Assistant y Proactivity dependen solo de ese puerto.
3. Expresar autorización, memoria, eventos y reloj como puertos.
4. Mantener modelos inmutables y dependencias de ejecución vacías.
5. Usar Python `>=3.10` de manera provisional hasta acordar la matriz de runtimes; evitar una dependencia de validación externa en Etapa 0.

## Consecuencias

Los adaptadores quedan para etapas posteriores. La autorización de memoria deberá comprobar propietario y contexto en cada operación. La versión mínima provisional debe revisarse antes de publicar el paquete.