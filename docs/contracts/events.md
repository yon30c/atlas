# Contrato de eventos

`DomainEvent` es un hecho inmutable con identificador, tipo, instante UTC, contexto de operación y datos serializables. `EventStore` define únicamente append y lectura por correlación. No se decide formato físico, broker, entrega ni política de retención en esta etapa.