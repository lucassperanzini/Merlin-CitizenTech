/*
 * Esfera holográfica do Jarvis, com Three.js e shaders próprios.
 *
 * Camadas: núcleo deformado por ruído (vertex shader) com borda luminosa e linhas de energia (fragment shader),
 * halo de brilho por trás, dois anéis e partículas. Cada estado (espera, ouvindo, pensando, falando) define
 * metas de cor, energia e velocidade, e os valores deslizam até elas a cada quadro, sem saltos.
 *
 * Otimizações: um único renderizador, poucos objetos, resolução limitada, e o desenho para quando a esfera
 * não está visível.
 */
(function () {
  "use strict";

  // Ruído simplex 3D (Ian McEwan, Ashima Arts, licença MIT)
  const RUIDO = `
    vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
    vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
    vec4 permute(vec4 x) { return mod289(((x * 34.0) + 10.0) * x); }
    vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
    float snoise(vec3 v) {
      const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
      const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
      vec3 i = floor(v + dot(v, C.yyy));
      vec3 x0 = v - i + dot(i, C.xxx);
      vec3 g = step(x0.yzx, x0.xyz);
      vec3 l = 1.0 - g;
      vec3 i1 = min(g.xyz, l.zxy);
      vec3 i2 = max(g.xyz, l.zxy);
      vec3 x1 = x0 - i1 + C.xxx;
      vec3 x2 = x0 - i2 + C.yyy;
      vec3 x3 = x0 - D.yyy;
      i = mod289(i);
      vec4 p = permute(permute(permute(
        i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0)) + i.x + vec4(0.0, i1.x, i2.x, 1.0));
      float n_ = 0.142857142857;
      vec3 ns = n_ * D.wyz - D.xzx;
      vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
      vec4 x_ = floor(j * ns.z);
      vec4 y_ = floor(j - 7.0 * x_);
      vec4 x = x_ * ns.x + ns.yyyy;
      vec4 y = y_ * ns.x + ns.yyyy;
      vec4 h = 1.0 - abs(x) - abs(y);
      vec4 b0 = vec4(x.xy, y.xy);
      vec4 b1 = vec4(x.zw, y.zw);
      vec4 s0 = floor(b0) * 2.0 + 1.0;
      vec4 s1 = floor(b1) * 2.0 + 1.0;
      vec4 sh = -step(h, vec4(0.0));
      vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
      vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
      vec3 p0 = vec3(a0.xy, h.x);
      vec3 p1 = vec3(a0.zw, h.y);
      vec3 p2 = vec3(a1.xy, h.z);
      vec3 p3 = vec3(a1.zw, h.w);
      vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
      p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
      vec4 m = max(0.5 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
      m = m * m;
      return 105.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
    }`;

  const VERTICE_NUCLEO = RUIDO + `
    uniform float uTempo;
    uniform float uEnergia;   // agitação geral do estado
    uniform float uVolume;    // volume da voz (sua ao ouvir, dele ao falar)
    uniform float uEscala;    // tamanho do ruído: mais detalhe ao processar
    varying vec3 vNormal;
    varying vec3 vVisao;
    varying vec3 vPosicao;
    varying float vDeslocamento;

    float relevo(vec3 p) {
      float largo = snoise(p * uEscala + vec3(0.0, uTempo * 0.35, uTempo * 0.2));
      float fino = snoise(p * uEscala * 3.1 - vec3(uTempo * 0.9)) * 0.35;
      return (largo + fino) * (0.03 + uEnergia * 0.07 + uVolume * 0.12);
    }

    void main() {
      vec3 p = position;
      float d = relevo(p);
      vec3 deslocado = p + normal * d;

      // Normal recalculada a partir de dois vizinhos, para a luz da borda acompanhar o relevo
      vec3 tangente = normalize(cross(normal, abs(normal.y) < 0.99 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0)));
      vec3 bitangente = cross(normal, tangente);
      float e = 0.01;
      vec3 vizinhoA = p + tangente * e;
      vec3 vizinhoB = p + bitangente * e;
      vizinhoA += normalize(vizinhoA) * relevo(vizinhoA);
      vizinhoB += normalize(vizinhoB) * relevo(vizinhoB);
      vec3 normalNova = normalize(cross(vizinhoA - deslocado, vizinhoB - deslocado));

      vec4 mv = modelViewMatrix * vec4(deslocado, 1.0);
      vNormal = normalize(normalMatrix * normalNova);
      vVisao = normalize(-mv.xyz);
      vPosicao = p;
      vDeslocamento = d;
      gl_Position = projectionMatrix * mv;
    }`;

  const FRAGMENTO_NUCLEO = `
    uniform float uTempo;
    uniform float uEnergia;
    uniform float uVolume;
    uniform float uVarredura;
    uniform vec3 uCorBorda;
    uniform vec3 uCorNucleo;
    varying vec3 vNormal;
    varying vec3 vVisao;
    varying vec3 vPosicao;
    varying float vDeslocamento;

    void main() {
      float alinhamento = abs(dot(normalize(vNormal), normalize(vVisao)));
      float borda = pow(1.0 - alinhamento, 2.4);                 // efeito Fresnel: a borda brilha

      // Linhas de energia correndo na horizontal, mais rápidas com mais energia
      float latitude = vPosicao.y * 22.0 - uTempo * (1.2 + uEnergia * 3.0);
      float linhas = smoothstep(0.9, 1.0, abs(sin(latitude))) * (0.25 + uEnergia * 0.35);

      // Malha de meridianos, discreta
      float longitude = atan(vPosicao.z, vPosicao.x) * 10.0;
      float malha = smoothstep(0.97, 1.0, abs(sin(longitude))) * 0.14;

      // Faixa de leitura que percorre a esfera de baixo para cima
      float faixa = fract(uTempo * uVarredura);
      float leitura = smoothstep(0.06, 0.0, abs(vPosicao.y * 0.5 + 0.5 - faixa)) * 0.6;

      float calor = clamp(vDeslocamento * 6.0 + 0.5, 0.0, 1.0);    // relevos altos ficam mais claros
      vec3 cor = mix(uCorNucleo, uCorBorda, borda + calor * 0.25);
      float intensidade = 0.06 + borda * 1.25 + linhas * 0.8 + malha + leitura * 0.7 + uVolume * 0.25;
      float alfa = clamp(0.05 + borda * 0.85 + linhas * 0.7 + malha + leitura * 0.5 + uVolume * 0.15, 0.0, 1.0);
      gl_FragColor = vec4(cor * intensidade, alfa);
    }`;

  const VERTICE_HALO = `
    varying vec3 vNormal;
    varying vec3 vVisao;
    void main() {
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      vNormal = normalize(normalMatrix * normal);
      vVisao = normalize(-mv.xyz);
      gl_Position = projectionMatrix * mv;
    }`;

  const FRAGMENTO_HALO = `
    uniform vec3 uCorBorda;
    uniform float uIntensidade;
    varying vec3 vNormal;
    varying vec3 vVisao;
    void main() {
      // Vista por dentro, a casca tem a borda em 0 e o centro em 1. O núcleo termina perto de 0,7:
      // o brilho nasce na borda de fora, cresce até o contorno do núcleo e some por trás dele.
      float profundidade = -dot(normalize(vNormal), normalize(vVisao));
      float halo = smoothstep(0.0, 0.66, profundidade) * (1.0 - smoothstep(0.66, 0.76, profundidade));
      halo = pow(halo, 1.6) * 0.55;
      gl_FragColor = vec4(uCorBorda * halo * uIntensidade, halo * uIntensidade);
    }`;

  const VERTICE_PARTICULAS = `
    uniform float uTempo;
    uniform float uEnergia;
    uniform float uPixel;
    attribute float aFase;
    varying float vBrilho;
    void main() {
      vec3 p = position * (1.0 + sin(uTempo * 0.8 + aFase) * 0.04 * (1.0 + uEnergia * 2.0));
      vec4 mv = modelViewMatrix * vec4(p, 1.0);
      vBrilho = 0.5 + 0.5 * sin(uTempo * 2.0 + aFase * 3.0);
      gl_PointSize = (1.0 + vBrilho * 1.5) * uPixel / -mv.z;
      gl_Position = projectionMatrix * mv;
    }`;

  const FRAGMENTO_PARTICULAS = `
    uniform vec3 uCorBorda;
    uniform float uOpacidade;
    varying float vBrilho;
    void main() {
      float d = length(gl_PointCoord - 0.5);
      float ponto = smoothstep(0.5, 0.0, d);
      gl_FragColor = vec4(uCorBorda * (0.6 + vBrilho), ponto * uOpacidade * (0.3 + vBrilho * 0.7));
    }`;

  // Metas de cada estado: as cores e números deslizam até elas
  const ESTADOS = {
    espera:   { borda: 0x35c4ff, nucleo: 0x062448, energia: 0.12, escala: 1.2, varredura: 0.12, giro: 0.1,  halo: 0.85 },
    ouvindo:  { borda: 0x35d6ff, nucleo: 0x06305c, energia: 0.22, escala: 1.3, varredura: 0.18, giro: 0.18, halo: 0.9 },
    pensando: { borda: 0xffb648, nucleo: 0x3a1c00, energia: 0.75, escala: 2.2, varredura: 0.55, giro: 0.7,  halo: 1.1 },
    falando:  { borda: 0x8ff0ff, nucleo: 0x0a3f8f, energia: 0.45, escala: 1.5, varredura: 0.3,  giro: 0.3,  halo: 1.2 },
    // Só as cores: com focos em alerta, valem para todos os estados (Esfera.alerta)
    alerta:   { borda: 0xff3b3b, nucleo: 0x4a0505, energia: 0.4,  escala: 1.5, varredura: 0.35, giro: 0.3,  halo: 1.15 },
  };
  const RESOLUCAO_MAXIMA = 1.75; // limite de pixels por ponto: telas muito densas não precisam de mais
  const SUAVIDADE = 4.0;         // quão rápido os valores chegam à meta (por segundo)
  let intervaloMinimo = 1000 / 60 - 1;  // monitores de 144 Hz ou mais não precisam de mais quadros

  let renderizador, cena, camera, grupo, nucleo, halo, aneis, particulas;
  let tela, ativa = false, rodando = false, ultimo = 0, tempo = 0;
  let estado = "ouvindo", volumeMicrofone = 0, envelope = null, emAlerta = false;
  const atual = { energia: 0.2, escala: 1.3, varredura: 0.2, giro: 0.2, halo: 0.9, volume: 0 };
  let corBorda, corNucleo, materialAnel;
  const METAS_DE_COR = {};  // criadas uma vez, para não gerar lixo de memória a cada quadro

  function criar(canvas) {
    tela = canvas;
    try {
      renderizador = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
    } catch (erro) {
      console.error("WebGL indisponível:", erro);
      return false;
    }
    renderizador.setClearColor(0x000000, 0);
    cena = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(35, 1, 0.1, 50);
    camera.position.set(0, 0, 5.2);
    grupo = new THREE.Group();
    cena.add(grupo);

    for (const [nome, e] of Object.entries(ESTADOS)) {
      METAS_DE_COR[nome] = { borda: new THREE.Color(e.borda), nucleo: new THREE.Color(e.nucleo) };
    }
    corBorda = new THREE.Color(ESTADOS.ouvindo.borda);
    corNucleo = new THREE.Color(ESTADOS.ouvindo.nucleo);
    const comuns = {
      uTempo: { value: 0 }, uEnergia: { value: 0.2 }, uVolume: { value: 0 },
      uCorBorda: { value: corBorda }, uCorNucleo: { value: corNucleo },
    };

    nucleo = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1, 48),
      new THREE.ShaderMaterial({
        vertexShader: VERTICE_NUCLEO, fragmentShader: FRAGMENTO_NUCLEO,
        uniforms: { ...comuns, uEscala: { value: 1.3 }, uVarredura: { value: 0.2 } },
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      }),
    );
    grupo.add(nucleo);

    halo = new THREE.Mesh(
      new THREE.SphereGeometry(1.42, 48, 48),
      new THREE.ShaderMaterial({
        vertexShader: VERTICE_HALO, fragmentShader: FRAGMENTO_HALO,
        uniforms: { uCorBorda: comuns.uCorBorda, uIntensidade: { value: 0.9 } },
        side: THREE.BackSide, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      }),
    );
    cena.add(halo);

    materialAnel = new THREE.MeshBasicMaterial({
      color: corBorda, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false,
    });
    aneis = [1.32, 1.5].map((raio, i) => {
      const anel = new THREE.Mesh(new THREE.TorusGeometry(raio, 0.006, 6, 160), materialAnel);
      anel.rotation.x = Math.PI / 2 + (i ? 0.5 : -0.35);
      anel.rotation.y = i ? -0.3 : 0.25;
      grupo.add(anel);
      return anel;
    });

    const quantidade = 700;
    const posicoes = new Float32Array(quantidade * 3);
    const fases = new Float32Array(quantidade);
    for (let i = 0; i < quantidade; i++) {
      // Pontos espalhados numa casca em volta do núcleo
      const u = Math.random() * 2 - 1, theta = Math.random() * Math.PI * 2, raio = 1.15 + Math.random() * 0.45;
      const s = Math.sqrt(1 - u * u);
      posicoes.set([raio * s * Math.cos(theta), raio * u, raio * s * Math.sin(theta)], i * 3);
      fases[i] = Math.random() * Math.PI * 2;
    }
    const geometria = new THREE.BufferGeometry();
    geometria.setAttribute("position", new THREE.BufferAttribute(posicoes, 3));
    geometria.setAttribute("aFase", new THREE.BufferAttribute(fases, 1));
    particulas = new THREE.Points(geometria, new THREE.ShaderMaterial({
      vertexShader: VERTICE_PARTICULAS, fragmentShader: FRAGMENTO_PARTICULAS,
      uniforms: { uTempo: comuns.uTempo, uEnergia: comuns.uEnergia, uPixel: { value: 8 },
                  uCorBorda: comuns.uCorBorda, uOpacidade: { value: 0.55 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    grupo.add(particulas);
    return true;
  }

  function ajustarTamanho() {
    const largura = tela.clientWidth, altura = tela.clientHeight;
    if (!largura || !altura) return;
    const escala = Math.min(window.devicePixelRatio || 1, RESOLUCAO_MAXIMA);
    if (tela.width !== Math.round(largura * escala) || tela.height !== Math.round(altura * escala)) {
      renderizador.setPixelRatio(escala);
      renderizador.setSize(largura, altura, false);
      camera.aspect = largura / altura;
      camera.updateProjectionMatrix();
      particulas.material.uniforms.uPixel.value = altura * escala * 0.012;
    }
  }

  function volumeDaFala(agora) {
    if (!envelope) return 0;
    const indice = Math.floor((agora - envelope.inicio) / 1000 / envelope.passo);
    if (indice < 0 || indice >= envelope.volumes.length) return 0;
    return envelope.volumes[indice];
  }

  function quadro(agora) {
    if (!ativa) { rodando = false; return; }
    if (agora - ultimo < intervaloMinimo) { requestAnimationFrame(quadro); return; }
    const dt = Math.min((agora - ultimo) / 1000, 0.05);
    ultimo = agora;
    tempo += dt;
    ajustarTamanho();

    const meta = ESTADOS[estado] || ESTADOS.ouvindo;
    const k = 1 - Math.exp(-SUAVIDADE * dt);
    for (const chave of ["energia", "escala", "varredura", "giro", "halo"]) {
      atual[chave] += (meta[chave] - atual[chave]) * k;
    }
    const volumeAlvo = estado === "falando" ? volumeDaFala(agora) : estado === "ouvindo" ? volumeMicrofone : 0;
    // Sobe rápido e desce devagar, como um medidor de áudio
    atual.volume += (volumeAlvo - atual.volume) * (volumeAlvo > atual.volume ? 0.45 : 0.12);
    // Com focos em alerta, a esfera fica vermelha em qualquer estado (o ritmo de cada estado continua)
    const cores = emAlerta ? METAS_DE_COR.alerta : METAS_DE_COR[estado] || METAS_DE_COR.ouvindo;
    corBorda.lerp(cores.borda, k);
    corNucleo.lerp(cores.nucleo, k);
    materialAnel.color.copy(corBorda);  // o material guarda uma cópia da cor, não a referência

    const u = nucleo.material.uniforms;
    u.uTempo.value = tempo;
    u.uEnergia.value = atual.energia;
    u.uVolume.value = atual.volume;
    u.uEscala.value = atual.escala;
    u.uVarredura.value = atual.varredura;
    halo.material.uniforms.uIntensidade.value = atual.halo + atual.volume * 0.5;
    materialAnel.opacity = 0.25 + atual.energia * 0.25 + atual.volume * 0.3;

    const pulso = 1 + atual.volume * 0.05;
    grupo.scale.setScalar(pulso);
    halo.scale.setScalar(pulso);
    grupo.rotation.y += dt * atual.giro;
    aneis[0].rotation.z += dt * atual.giro * 1.6;
    aneis[1].rotation.z -= dt * atual.giro * 1.1;
    particulas.rotation.y -= dt * atual.giro * 0.5;

    renderizador.render(cena, camera);
    window.Esfera.quadros++;
    requestAnimationFrame(quadro);
  }

  window.Esfera = {
    ok: false,
    quadros: 0,  // quadros desenhados, para medir o desempenho
    iniciar(canvas) {
      this.ok = typeof THREE !== "undefined" && criar(canvas);
      return this.ok;
    },
    ligar() {
      if (!this.ok) return;
      ativa = true;
      if (!rodando) { rodando = true; ultimo = performance.now(); requestAnimationFrame(quadro); }
    },
    desligar() { ativa = false; },  // sem desenho, a placa de vídeo fica livre
    // Na bolinha de espera, poucos quadros bastam: ela fica o dia todo na tela
    limitarQuadros(porSegundo) { intervaloMinimo = 1000 / porSegundo - 1; },
    definirEstado(novo) {
      estado = novo;
      if (novo !== "falando") envelope = null;
    },
    definirVolume(nivel) { volumeMicrofone = nivel; },
    alerta(ligado) { emAlerta = !!ligado; },  // recursos/janela.html: definirAlerta
    falar(volumes, passo) { envelope = { volumes, passo, inicio: performance.now() }; },
  };
})();
