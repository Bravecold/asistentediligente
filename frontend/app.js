const api = window.ASISTENTE_CONFIG?.apiUrl || "http://localhost:8000";
const cards = document.querySelector("#procedures");
const select = document.querySelector("#procedure-select");
const form = document.querySelector("#request-form");
const result = document.querySelector("#form-result");

const fallback = [
  {id:"ops-cita-eps",category:"Salud",name:"Solicitar cita médica",entity:"EPS (según afiliación)",risk:"medium",required_items:["Documento","Tipo de cita","Disponibilidad"]},
  {id:"ops-medicamentos",category:"Salud",name:"Orientar solicitud de medicamentos",entity:"EPS/IPS (según afiliación)",risk:"high",required_items:["Fórmula vigente","Documento"]},
  {id:"ops-vus-movilidad",category:"Movilidad",name:"Cita para trámite de movilidad",entity:"Ventanilla Única de Servicios",risk:"low",required_items:["Documento","Datos del trámite"]}
];

function render(items) {
  const risk = {low:"Riesgo bajo",medium:"Riesgo medio",high:"Datos sensibles"};
  cards.innerHTML = items.map(p => `<article class="card"><div><span>${p.category}</span><span class="risk ${p.risk}">${risk[p.risk]}</span></div><h3>${p.name}</h3><p>${p.entity}</p><small>Requisitos: ${p.required_items.join(" · ")}</small></article>`).join("");
  select.innerHTML = `<option value="">Selecciona una opción</option>` + items.map(p => `<option value="${p.id}">${p.name} — ${p.entity}</option>`).join("");
}

fetch(`${api}/api/procedures`).then(r => r.ok ? r.json() : Promise.reject()).then(render).catch(() => render(fallback));

form.addEventListener("submit", async event => {
  event.preventDefault(); result.textContent = "Registrando…"; result.className = "";
  const data = Object.fromEntries(new FormData(form));
  data.accept_privacy = Boolean(data.accept_privacy);
  data.accept_sensitive_data = Boolean(data.accept_sensitive_data);
  try {
    const response = await fetch(`${api}/api/requests`, {method:"POST",headers:{"Content-Type":"application/json","X-Demo-Role":"customer"},body:JSON.stringify(data)});
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "No fue posible registrar la solicitud");
    result.textContent = `Solicitud registrada: ${body.id.slice(0,8).toUpperCase()}. Estado: recibida.`; result.className = "success"; form.reset();
  } catch (error) { result.textContent = error.message; result.className = "error"; }
});

