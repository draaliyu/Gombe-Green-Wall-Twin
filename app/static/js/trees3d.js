import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js";

function enableSway(material, factor) {
  const uniforms = { time: { value: 0 }, strength: { value: 0.08 }, dir: { value: new THREE.Vector2(1, 0) } };
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uSwayTime = uniforms.time;
    shader.uniforms.uSwayStrength = uniforms.strength;
    shader.uniforms.uSwayDir = uniforms.dir;
    shader.vertexShader = `uniform float uSwayTime;\nuniform float uSwayStrength;\nuniform vec2 uSwayDir;\n${shader.vertexShader}`;
    shader.vertexShader = shader.vertexShader.replace(
      "#include <begin_vertex>",
      `#include <begin_vertex>
       float swayPhase = uSwayTime;
       #ifdef USE_INSTANCING
         swayPhase += instanceMatrix[3].x * 0.0023 + instanceMatrix[3].z * 0.0017;
       #endif
       float heightWeight = clamp(position.y / 5.0, 0.0, 1.0);
       float sway = sin(swayPhase + position.y * 0.75) * uSwayStrength * heightWeight * ${factor.toFixed(3)};
       transformed.x += uSwayDir.x * sway;
       transformed.z += uSwayDir.y * sway;`,
    );
    material.userData.swayShader = shader;
  };
  material.customProgramCacheKey = () => `green-wall-sway-${factor}`;
  material.userData.swayUniforms = uniforms;
  return material;
}

export class TreeLayer {
  constructor(id, origin) {
    this.id = id;
    this.type = "custom";
    this.renderingMode = "3d";
    this.origin = origin;
    this.visible = true;
    this.trees = [];
    this.version = -1;
    this.windSpeed = 0;
    this.windDirection = 0;
    this.daylight = true;
    this.cloudCover = 0;
    this.temperature = 30;
    this.clock = new THREE.Clock();
    this.materials = [];
  }

  onAdd(map, gl) {
    this.map = map;
    this.camera = new THREE.Camera();
    this.scene = new THREE.Scene();
    this.renderer = new THREE.WebGLRenderer({ canvas: map.getCanvas(), context: gl, antialias: true });
    this.renderer.autoClear = false;
    this.hemiLight = new THREE.HemisphereLight(0xcfffe8, 0x7a5b37, 1.75);
    this.scene.add(this.hemiLight);
    this.sunLight = new THREE.DirectionalLight(0xfff2c6, 2.35);
    this.sunLight.position.set(80, -120, 180);
    this.scene.add(this.sunLight);
    const rim = new THREE.DirectionalLight(0x5fd9b0, 0.55);
    rim.position.set(-90, 55, 120);
    this.scene.add(rim);
    this.originMercator = maplibregl.MercatorCoordinate.fromLngLat(this.origin, 0);
    this.meterScale = this.originMercator.meterInMercatorCoordinateUnits();
    this.group = new THREE.Group();
    this.scene.add(this.group);
    this.rebuild();
  }

  setTrees(trees, version) {
    if (version === this.version) return;
    this.version = version;
    this.trees = Array.isArray(trees) ? trees : [];
    if (this.group) this.rebuild();
  }

  setWeather(weather) {
    this.windSpeed = Math.max(0, Number(weather?.wind_speed_mps) || 0);
    this.windDirection = (Number(weather?.wind_direction_deg) || 0) * Math.PI / 180;
    this.daylight = weather?.is_daylight !== false;
    this.cloudCover = Math.max(0, Math.min(100, Number(weather?.cloud_cover_percent) || 0));
    this.temperature = Number(weather?.temperature_c) || 30;
  }

  setVisible(visible) {
    this.visible = visible;
    if (this.group) this.group.visible = visible;
  }

  disposeGroup() {
    while (this.group.children.length) {
      const object = this.group.children.pop();
      object.geometry?.dispose?.();
      object.material?.dispose?.();
    }
    this.materials = [];
  }

  rebuild() {
    this.disposeGroup();
    if (!this.trees.length) return;
    const count = this.trees.length;
    const trunkGeometry = new THREE.CylinderGeometry(0.16, 0.34, 2.8, 7);
    trunkGeometry.translate(0, 1.4, 0);
    const branchGeometry = new THREE.CylinderGeometry(0.06, 0.12, 1.45, 5);
    branchGeometry.rotateZ(-0.55);
    branchGeometry.translate(0.55, 2.35, 0);
    const branchOppositeGeometry = new THREE.CylinderGeometry(0.05, 0.11, 1.25, 5);
    branchOppositeGeometry.rotateZ(0.62);
    branchOppositeGeometry.translate(-0.46, 2.18, 0.16);
    const crownGeometry = new THREE.IcosahedronGeometry(1.0, 1);
    crownGeometry.scale(1.18, 0.92, 1.08);
    crownGeometry.translate(0, 3.35, 0);
    const crownSideGeometry = new THREE.IcosahedronGeometry(0.72, 1);
    crownSideGeometry.scale(1.15, 0.85, 1.0);
    crownSideGeometry.translate(0.78, 3.05, 0.18);

    const trunkMaterial = enableSway(new THREE.MeshStandardMaterial({ color: 0x7b5133, roughness: 0.96 }), 0.22);
    const branchMaterial = enableSway(new THREE.MeshStandardMaterial({ color: 0x735038, roughness: 0.95 }), 0.42);
    const branchOppositeMaterial = enableSway(new THREE.MeshStandardMaterial({ color: 0x6f4b31, roughness: 0.96 }), 0.46);
    const crownMaterial = enableSway(new THREE.MeshStandardMaterial({ color: 0x36b56e, roughness: 0.86, vertexColors: true }), 1.0);
    const crownSideMaterial = enableSway(new THREE.MeshStandardMaterial({ color: 0x4dc67b, roughness: 0.86, vertexColors: true }), 1.18);
    this.materials = [trunkMaterial, branchMaterial, branchOppositeMaterial, crownMaterial, crownSideMaterial];

    const trunks = new THREE.InstancedMesh(trunkGeometry, trunkMaterial, count);
    const branches = new THREE.InstancedMesh(branchGeometry, branchMaterial, count);
    const oppositeBranches = new THREE.InstancedMesh(branchOppositeGeometry, branchOppositeMaterial, count);
    const crowns = new THREE.InstancedMesh(crownGeometry, crownMaterial, count);
    const sideCrowns = new THREE.InstancedMesh(crownSideGeometry, crownSideMaterial, count);
    [trunks, branches, oppositeBranches, crowns, sideCrowns].forEach((mesh) => { mesh.frustumCulled = false; });

    const matrix = new THREE.Matrix4();
    const position = new THREE.Vector3();
    const quaternion = new THREE.Quaternion();
    const scale = new THREE.Vector3();
    const color = new THREE.Color();
    const axis = new THREE.Vector3(0, 1, 0);
    this.trees.forEach((tree, index) => {
      const mercator = maplibregl.MercatorCoordinate.fromLngLat([tree.longitude, tree.latitude], 0);
      const x = (mercator.x - this.originMercator.x) / this.meterScale;
      const z = -(mercator.y - this.originMercator.y) / this.meterScale;
      const health = Math.max(0.06, Math.min(1, Number(tree.health) || 0.1));
      const heightScale = Math.max(0.22, (Number(tree.height_m) || 3) / 7.0);
      const crownScale = Math.max(0.38, (Number(tree.crown_m) || 1.5) / 3.2);
      position.set(x, 0, z);
      quaternion.setFromAxisAngle(axis, (index * 1.618) % (Math.PI * 2));
      scale.set(0.72 + health * 0.42, heightScale, 0.72 + health * 0.42);
      matrix.compose(position, quaternion, scale);
      trunks.setMatrixAt(index, matrix);
      branches.setMatrixAt(index, matrix);
      oppositeBranches.setMatrixAt(index, matrix);
      scale.set(crownScale * (0.72 + health * 0.55), heightScale * (0.82 + health * 0.35), crownScale * (0.72 + health * 0.55));
      matrix.compose(position, quaternion, scale);
      crowns.setMatrixAt(index, matrix);
      sideCrowns.setMatrixAt(index, matrix);
      color.setHSL(0.055 + health * 0.29, 0.62 + health * 0.18, 0.23 + health * 0.26);
      crowns.setColorAt(index, color);
      const sideColor = color.clone().offsetHSL(0.01, -0.04, 0.06);
      sideCrowns.setColorAt(index, sideColor);
    });
    [trunks, branches, oppositeBranches, crowns, sideCrowns].forEach((mesh) => { mesh.instanceMatrix.needsUpdate = true; });
    if (crowns.instanceColor) crowns.instanceColor.needsUpdate = true;
    if (sideCrowns.instanceColor) sideCrowns.instanceColor.needsUpdate = true;
    this.group.add(trunks, branches, oppositeBranches, crowns, sideCrowns);
  }

  render(gl, args) {
    if (!this.group || !this.visible) return;
    const elapsed = this.clock.getElapsedTime();
    if (this.sunLight && this.hemiLight) {
      const cloudDim = 1 - this.cloudCover / 170;
      this.sunLight.intensity = this.daylight ? 1.25 + cloudDim * 1.45 : 0.18;
      this.sunLight.color.set(this.daylight ? 0xffefbf : 0x92b7ff);
      this.hemiLight.intensity = this.daylight ? 1.15 + cloudDim * 0.75 : 0.52;
      this.hemiLight.color.set(this.daylight ? 0xd7fff0 : 0x8eace8);
    }
    const strength = Math.min(0.48, 0.035 + this.windSpeed * 0.025);
    const dirX = Math.sin(this.windDirection);
    const dirY = Math.cos(this.windDirection);
    this.materials.forEach((material) => {
      const uniforms = material.userData.swayUniforms;
      if (uniforms) {
        uniforms.time.value = elapsed * (0.85 + this.windSpeed * 0.08);
        uniforms.strength.value = strength;
        uniforms.dir.value.set(dirX, dirY);
      }
    });
    const modelMatrix = new THREE.Matrix4()
      .makeTranslation(this.originMercator.x, this.originMercator.y, this.originMercator.z)
      .scale(new THREE.Vector3(this.meterScale, -this.meterScale, this.meterScale))
      .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2));
    const rawMatrix = args?.defaultProjectionData?.mainMatrix || args?.mainMatrix || args;
    if (!rawMatrix || typeof rawMatrix.length !== "number" || rawMatrix.length !== 16) return;
    const mapMatrix = new THREE.Matrix4().fromArray(rawMatrix);
    this.camera.projectionMatrix = mapMatrix.multiply(modelMatrix);
    this.renderer.resetState();
    this.renderer.render(this.scene, this.camera);
    this.map.triggerRepaint();
  }
}
