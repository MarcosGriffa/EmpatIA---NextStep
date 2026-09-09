import Link from "next/link";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

// Política de privacidad (09/09/2026). Escrita para ser leída y
// entendida, no para cubrirnos legalmente con letra chica — refleja
// exactamente lo que el código hace hoy (ver api/matching.py,
// api/storage_backends/supabase_backend.py, semantic_match.py, geo.py:
// la redacción de dirección y la ubicación a nivel ciudad).
//
// Un criterio importante al redactarla: "no compartimos tus datos con
// terceros" hubiera sido falso tal cual — el CV SÍ viaja a Groq y Cohere
// para que la IA lo entienda, eso es cómo funciona el matching. La
// distinción real (y la que hace esta página) es entre "le pasamos tu
// dato a un proveedor para que el servicio funcione" (eso sí pasa, se
// lista abajo con nombre y apellido) y "vendemos o compartimos tu dato
// con alguien que lo use para sus propios fines, tipo publicidad" (eso
// no pasa nunca).
export default function PrivacidadPage() {
  return (
    <>
      <Header />
      <main className="flex-1">
        <div className="mx-auto max-w-2xl px-6 py-16">
          <Link href="/" className="text-sm font-semibold text-terracota">
            ← Volver al inicio
          </Link>

          <h1 className="mt-4 text-3xl font-extrabold text-brown-title">Política de Privacidad</h1>
          <p className="mt-3 text-brown-body">
            Última actualización: 9 de septiembre de 2026. La escribimos para que se entienda,
            no para llenarla de letra chica — si algo no queda claro, escribinos.
          </p>

          <div className="mt-10 flex flex-col gap-8">
            <section>
              <h2 className="text-xl font-bold text-brown-title">Qué datos guardamos</h2>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-brown-body">
                <li>
                  <strong className="text-brown-title">Tu cuenta:</strong> el mail con el que te registrás. Si
                  entrás con Google, también tu nombre y tu foto de perfil — nos los pasa Google
                  automáticamente, nunca vemos tu contraseña de Google.
                </li>
                <li>
                  <strong className="text-brown-title">Tu CV:</strong> el texto que subís, y el perfil que arma
                  la IA a partir de él (área, nivel de experiencia, habilidades). Antes de guardarlo,
                  borramos automáticamente la dirección exacta (calle, altura, piso) si el CV la
                  trae — reemplazándola por &ldquo;[dirección omitida]&rdquo;.
                </li>
                <li>
                  <strong className="text-brown-title">Tu zona</strong> (ciudad o partido, por ejemplo
                  &ldquo;Vicente López&rdquo; o &ldquo;CABA&rdquo;): la usamos para priorizar ofertas
                  presenciales o híbridas cerca tuyo. La sacamos de tu CV o del menú opcional al subirlo;
                  guardamos sólo el nivel ciudad/partido, <strong className="text-brown-title">nunca la
                  dirección exacta</strong>. Si no la tenemos, no pasa nada — no se penaliza ninguna oferta.
                </li>
                <li>
                  <strong className="text-brown-title">Tus resultados:</strong> las ofertas que te mostramos en
                  cada búsqueda, con tu puntaje de compatibilidad con cada una.
                </li>
                <li>
                  <strong className="text-brown-title">Qué ofertas marcaste como aplicadas.</strong>
                </li>
                <li>
                  <strong className="text-brown-title">Una cookie técnica</strong> para mantener tu sesión
                  iniciada. No usamos cookies de rastreo publicitario, ni de terceros para seguirte por
                  otros sitios.
                </li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-brown-title">Para qué los usamos</h2>
              <p className="mt-3 text-brown-body">
                Únicamente para hacer funcionar el servicio: entender tu perfil, buscar ofertas que
                matcheen, explicarte por qué (o por qué no) cada una, y guardar tus resultados para que
                los veas de nuevo, desde cualquier dispositivo, sin tener que resubir el CV cada vez.
                Nada de publicidad, nada de marketing.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-brown-title">Quién más toca tus datos, y por qué</h2>
              <p className="mt-3 text-brown-body">
                Para que el matching funcione, algunos datos pasan por proveedores que usamos para
                procesarlos — no son terceros que los usen para algo propio:
              </p>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-brown-body">
                <li>
                  <strong className="text-brown-title">Groq y Cohere</strong> (inteligencia artificial): reciben
                  el texto de tu CV y de las ofertas, solo para entenderlos y compararlos. No lo usan para
                  entrenar nada propio ni para ningún otro fin.
                </li>
                <li>
                  <strong className="text-brown-title">Supabase</strong>: es donde vive la base de datos y el
                  sistema de cuentas — es infraestructura, no alguien mirando tus datos.
                </li>
                <li>
                  <strong className="text-brown-title">Los portales de empleo</strong> (Computrabajo, Jooble y
                  el resto): reciben palabras clave de búsqueda derivadas de tu perfil (por ejemplo
                  &ldquo;analista de datos junior&rdquo;), nunca tu CV completo ni tus datos personales.
                </li>
                <li>
                  <strong className="text-brown-title">Google</strong>: solo si elegís entrar con Google — son
                  ellos los que te identifican en ese caso.
                </li>
              </ul>
              <p className="mt-3 text-brown-body">
                <strong className="text-brown-title">Nunca vendemos tus datos</strong> ni se los compartimos a
                nadie más.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-brown-title">Cuánto tiempo los guardamos</h2>
              <p className="mt-3 text-brown-body">
                Mientras tu cuenta esté activa. Si querés que la borremos, es el siguiente punto.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-brown-title">Tus derechos</h2>
              <p className="mt-3 text-brown-body">
                Podés pedirnos en cualquier momento ver qué guardamos de vos, corregirlo, o borrarlo
                entero — escribinos a{" "}
                <a href="mailto:marcosgriffa04@gmail.com" className="font-semibold text-terracota">
                  marcosgriffa04@gmail.com
                </a>{" "}
                y lo resolvemos a mano (todavía no hay un botón de autoservicio para esto).
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-brown-title">Cambios a esta política</h2>
              <p className="mt-3 text-brown-body">
                Si algo importante cambia, lo vamos a actualizar acá mismo, en esta misma página.
              </p>
            </section>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
