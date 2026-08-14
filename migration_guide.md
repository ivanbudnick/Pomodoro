# Guía de Integración Pomodoro para 3D-Moai (Next.js / Supabase)

Esta guía detalla cómo integrar el firmware del Pomodoro ESP32 v1.0.5 en tu plataforma web `3d-moai.vercel.app`.

---

## 1. Endpoints Requeridos por la ESP32

El Pomodoro ESP32 funciona como un cliente HTTP puro. Consume y reporta datos a los siguientes dos endpoints:

### A. Obtener Configuración de Tiempos
* **Método**: `GET`
* **Ruta**: `/api/pomodoro/config`
* **Query Params**: `?device_id=240ac4041b30`
* **Comportamiento recomendado (Auto-Registro)**: Si la base de datos no tiene una fila para este `device_id`, el backend debe crearla automáticamente en la tabla `dispositivos` (con un `user_id` temporal o `NULL`) y en `pomodoro_configuraciones` con valores por defecto. De este modo, la ESP32 se auto-registra al encenderse por primera vez.
* **Respuesta Exitosa (200 OK - JSON)**:
  ```json
  {
    "tiempo_focus": 1500,
    "tiempo_descanso_corto": 300,
    "tiempo_descanso_largo": 900,
    "descanso_largo_activo": true,
    "ciclos_para_descanso_largo": 4
  }
  ```

### B. Registrar Evento de Telemetría (Estadísticas)
* **Método**: `POST`
* **Ruta**: `/api/pomodoro/stats`
* **Cuerpo (JSON)**:
  ```json
  {
    "device_id": "240ac4041b30",
    "tipo_sesion": "focus",
    "ciclo_num": 1,
    "duracion_s": 1500,
    "forzado": 0
  }
  ```
* **Respuesta Exitosa (200 OK - JSON)**:
  ```json
  {
    "status": "success",
    "message": "Estadística registrada correctamente."
  }
  ```

---

## 2. Ejemplo de Implementación en Next.js (API Routes - Node.js)

A continuación tienes ejemplos de código para colocar en tu carpeta `pages/api/pomodoro/` o `app/api/pomodoro/` en tu repositorio de `3d-moai`.

### GET `/api/pomodoro/config/route.ts` (Next.js App Router)
```typescript
import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const deviceId = searchParams.get('device_id');

  if (!deviceId) {
    return NextResponse.json({ error: 'Falta device_id' }, { status: 400 });
  }

  // 1. Intentar obtener la configuración
  let { data: config, error } = await supabase
    .from('pomodoro_configuraciones')
    .select('tiempo_focus, tiempo_descanso_corto, tiempo_descanso_largo, descanso_largo_activo, ciclos_para_descanso_largo')
    .eq('device_id', deviceId)
    .single();

  // 2. Si no existe, auto-registrar el dispositivo y crear la configuración por defecto
  if (error || !config) {
    // Registrar el hardware con user_id null por ahora
    await supabase
      .from('dispositivos')
      .insert([{ device_id: deviceId, user_id: null, product_type: 'Pomodoro Pro' }]);

    // Crear la configuración inicial por defecto (25min focus, 5min break, 15min long break)
    const defaultConfig = {
      device_id: deviceId,
      tiempo_focus: 1500,
      tiempo_descanso_corto: 300,
      tiempo_descanso_largo: 900,
      descanso_largo_activo: true,
      ciclos_para_descanso_largo: 4
    };

    await supabase
      .from('pomodoro_configuraciones')
      .insert([defaultConfig]);

    config = {
      tiempo_focus: defaultConfig.tiempo_focus,
      tiempo_descanso_corto: defaultConfig.tiempo_descanso_corto,
      tiempo_descanso_largo: defaultConfig.tiempo_descanso_largo,
      descanso_largo_activo: defaultConfig.descanso_largo_activo,
      ciclos_para_descanso_largo: defaultConfig.ciclos_para_descanso_largo
    };
  }

  // 3. Registrar ping de actividad
  await supabase
    .from('dispositivos')
    .update({ last_seen_at: new Date().toISOString() })
    .eq('device_id', deviceId);

  return NextResponse.json(config);
}
```

### POST `/api/pomodoro/stats/route.ts` (Next.js App Router)
```typescript
import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { device_id, tipo_sesion, ciclo_num, duracion_s, forzado } = body;

    if (!device_id || !tipo_sesion) {
      return NextResponse.json({ error: 'Campos requeridos faltantes' }, { status: 400 });
    }

    // Insertar reporte en la base de datos
    const { error } = await supabase
      .from('pomodoro_estadisticas')
      .insert([{
        device_id,
        tipo_sesion,
        ciclo_num: ciclo_num || 0,
        duracion_s: duracion_s || 0,
        forzado: forzado || 0
      }]);

    if (error) throw error;

    // Actualizar última actividad del dispositivo
    await supabase
      .from('dispositivos')
      .update({ last_seen_at: new Date().toISOString() })
      .eq('device_id', device_id);

    return NextResponse.json({ status: 'success', message: 'Estadística registrada correctamente.' });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
```

---

## 3. Vistas del Panel de Control en 3D-Moai

### A. Vista de Administrador (Fleet Management)
Para monitorear todos los Pomodoros vendidos o activos, tu panel administrador puede hacer la siguiente consulta SQL / Supabase:
```javascript
// Obtener todos los dispositivos registrados, su estado de conexión y su dueño
const { data, error } = await supabase
  .from('dispositivos')
  .select('device_id, user_id, product_type, registered_at, last_seen_at');
```
* **Estado "Online"**: Si `last_seen_at` ocurrió en los últimos 5 minutos, puedes pintarle un indicador verde en la tabla para saber que está encendido.
* **Fácil asignación**: Si un dispositivo tiene `user_id: null`, puedes proveer un botón en tu UI de Admin para asignarlo al correo o `id` del cliente que lo compró.

### B. Vista de Usuario (Dashboard Personal)
Para que un cliente edite sus tiempos de Focus y descansos:
1. Filtra los dispositivos donde `user_id` sea igual al ID del usuario autenticado en NextAuth/Supabase Auth.
2. Muestra los inputs cargados con `pomodoro_configuraciones` para ese `device_id`.
3. Al guardar cambios, actualiza los registros en `pomodoro_configuraciones` y añade `updated_at: new Date()`. La ESP32 los leerá la próxima vez que inicie una sesión (al pulsar el botón "Comenzar").
