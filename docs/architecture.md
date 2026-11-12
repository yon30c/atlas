# Arquitectura de Etapa 0

## Límites

`core` define identidad, contexto, enums y errores del dominio.

`ports` define las dependencias que el núcleo necesita.

`memory`, `assistant` y `proactivity` contienen modelos y contratos, no adaptadores externos.

El núcleo no debe depender directamente de infraestructura, proveedores externos ni mecanismos concretos de persistencia.

## Identidad y contexto

Cada operación utiliza un `OperationContext` explícito e inmutable.

El contexto identifica al actor mediante `Identity` y contiene información de atribución, correlación, origen, delegación, proyecto, entorno, propósito y clasificación.

Los campos de proyecto y entorno pueden estar ausentes en esta etapa. Su ausencia no debe interpretarse como autorización.

El contexto describe una operación, pero no concede permisos.

## Memoria

`MemoryGateway` es la única frontera para consultar y proponer cambios de memoria.

Ningún módulo de dominio recibe conexiones, repositorios físicos o credenciales de almacenamiento.

El puerto permite obtener memorias visibles para un contexto e ingresar una propuesta.

La implementación debe imponer autorización y aislamiento de propietario antes de acceder al almacenamiento.

Una propuesta no se convierte automáticamente en memoria activa.

## Autorización

La autorización es un puerto explícito.

Las operaciones protegidas no deben asumir permisos por la identidad, el contexto, el origen de una solicitud o la pertenencia a un proyecto.

La autorización debe comprobarse en la frontera correspondiente antes de ejecutar una operación protegida.

## Eventos y tiempo

La persistencia de eventos y el reloj son dependencias expresadas mediante puertos.

Los eventos de dominio son inmutables y utilizan instantes UTC.

La infraestructura de almacenamiento, entrega y retención queda fuera de esta etapa.

## Etapa posterior

Los puertos no tienen adaptadores en esta etapa.

No hay decisiones definitivas de base de datos, transporte, proveedores de modelos ni despliegue.
