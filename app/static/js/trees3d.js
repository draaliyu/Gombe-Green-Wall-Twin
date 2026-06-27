import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js";

export class TreeLayer {
  constructor(id, origin) {
    this.id = id;
    this.type = "custom";
    this.renderingMode = "3d";
    this.origin = origin;
    this.visible = true;
    this.trees = [];
    this.version = -1;
  }

  onAdd(map, gl) {
    this.map = map;
    this.camera = new THREE.Camera();
    this.scene = new THREE.Scene();
    this.renderer = new THREE.WebGLRenderer({ canvas: map.getCanvas(), context: gl, antialias: true });
    this.renderer.autoClear = false;
    this.scene.add(new THREE.AmbientLight(0xc7ffe2, 1.25));
    const sun = new THREE.DirectionalLight(0xfff2c6, 2.1);
    sun.position.set(80, -120, 180);
    this.scene.add(sun);

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

  setVisible(visible) {
    this.visible = visible;
    if (this.group) this.group.visible = visible;
  }

  rebuild() {
    while (this.group.children.length) {
      const object = this.group.children.pop();
      object.geometry?.dispose?.();
      object.material?.dispose?.();
    }
    if (!this.trees.length) return;

    const count = this.trees.length;
    const trunkGeometry = new THREE.CylinderGeometry(0.18, 0.28, 1.9, 6);
    trunkGeometry.translate(0, 0.95, 0);
    const crownGeometry = new THREE.ConeGeometry(1.15, 2.6, 7);
    crownGeometry.translate(0, 3.05, 0);
    const trunkMaterial = new THREE.MeshStandardMaterial({ color: 0x7c5534, roughness: 0.95 });
    const crownMaterial = new THREE.MeshStandardMaterial({ color: 0x39c678, roughness: 0.82, vertexColors: true });
    const trunks = new THREE.InstancedMesh(trunkGeometry, trunkMaterial, count);
    const crowns = new THREE.InstancedMesh(crownGeometry, crownMaterial, count);
    trunks.frustumCulled = false;
    crowns.frustumCulled = false;

    const matrix = new THREE.Matrix4();
    const position = new THREE.Vector3();
    const quaternion = new THREE.Quaternion();
    const scale = new THREE.Vector3();
    const color = new THREE.Color();
    this.trees.forEach((tree, index) => {
      const mercator = maplibregl.MercatorCoordinate.fromLngLat([tree.longitude, tree.latitude], 0);
      const x = (mercator.x - this.originMercator.x) / this.meterScale;
      const z = -(mercator.y - this.originMercator.y) / this.meterScale;
      const health = Math.max(0.08, Math.min(1, Number(tree.health) || 0.1));
      const heightScale = Math.max(0.25, (Number(tree.height_m) || 3) / 6.0);
      position.set(x, 0, z);
      quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), (index * 1.618) % (Math.PI * 2));
      scale.set(0.8 + health * 0.55, heightScale, 0.8 + health * 0.55);
      matrix.compose(position, quaternion, scale);
      trunks.setMatrixAt(index, matrix);
      crowns.setMatrixAt(index, matrix);
      color.setHSL(0.06 + health * 0.28, 0.72, 0.24 + health * 0.25);
      crowns.setColorAt(index, color);
    });
    trunks.instanceMatrix.needsUpdate = true;
    crowns.instanceMatrix.needsUpdate = true;
    if (crowns.instanceColor) crowns.instanceColor.needsUpdate = true;
    this.group.add(trunks, crowns);
  }

  render(gl, args) {
    if (!this.group || !this.visible) return;
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
