"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  Box,
  Play,
  Pause,
  RotateCcw,
  ZoomIn,
  ZoomOut,
  Layers,
  AlertCircle,
  CheckCircle,
  Info,
} from "lucide-react";

interface KnowledgeNode {
  id: number;
  type: string;
  title: string;
  content: string;
  confidence: number;
  occurrence: number;
  tags: string[];
  position: THREE.Vector3;
}

interface PRModule {
  id: string;
  number: number;
  title: string;
  status: "incoming" | "snapping" | "snapped" | "rejected";
  filesChanged: number;
  additions: number;
  deletions: number;
  matchScore: number;
  targetPosition: THREE.Vector3;
  startPosition: THREE.Vector3;
  currentPosition: THREE.Vector3;
  rotation: THREE.Euler;
  color: THREE.Color;
}

const TYPE_COLORS: Record<string, string> = {
  code_standard: "#3b82f6",
  common_issue: "#ef4444",
  historical_dispute: "#eab308",
  project_context: "#22c55e",
  best_practice: "#a855f7",
};

const TYPE_ICONS: Record<string, string> = {
  code_standard: "📐",
  common_issue: "⚠️",
  historical_dispute: "💬",
  project_context: "🌐",
  best_practice: "⭐",
};

export default function Sandbox3D({
  knowledgeItems = [],
  onNodeSelect,
}: {
  knowledgeItems?: Array<{
    id: number;
    knowledge_type: string;
    title: string;
    content: string;
    confidence_score: number;
    occurrence_count: number;
    tags?: string[];
  }>;
  onNodeSelect?: (node: KnowledgeNode) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const nodesGroupRef = useRef<THREE.Group | null>(null);
  const prModulesGroupRef = useRef<THREE.Group | null>(null);

  const [selectedNode, setSelectedNode] = useState<KnowledgeNode | null>(null);
  const [isAnimating, setIsAnimating] = useState(true);
  const [autoRotate, setAutoRotate] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [prModules, setPrModules] = useState<PRModule[]>([]);
  const [activePR, setActivePR] = useState<PRModule | null>(null);

  const [nodes, setNodes] = useState<KnowledgeNode[]>([]);
  const nodeMeshesRef = useRef<Map<number, THREE.Mesh>>(new Map());
  const prMeshesRef = useRef<Map<string, THREE.Group>>(new Map());
  const raycasterRef = useRef<THREE.Raycaster>(new THREE.Raycaster());
  const mouseRef = useRef<THREE.Vector2>(new THREE.Vector2());

  const initScene = useCallback(() => {
    if (!containerRef.current) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f172a);
    scene.fog = new THREE.FogExp2(0x0f172a, 0.015);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(
      60,
      containerRef.current.clientWidth / containerRef.current.clientHeight,
      0.1,
      1000
    );
    camera.position.set(25, 20, 25);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
    });
    renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    containerRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.enablePan = true;
    controls.minDistance = 5;
    controls.maxDistance = 100;
    controls.autoRotate = autoRotate;
    controls.autoRotateSpeed = 0.5;
    controlsRef.current = controls;

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(20, 30, 20);
    directionalLight.castShadow = true;
    directionalLight.shadow.mapSize.width = 2048;
    directionalLight.shadow.mapSize.height = 2048;
    scene.add(directionalLight);

    const pointLight1 = new THREE.PointLight(0x8b5cf6, 0.5, 50);
    pointLight1.position.set(-20, 10, -20);
    scene.add(pointLight1);

    const pointLight2 = new THREE.PointLight(0x06b6d4, 0.3, 50);
    pointLight2.position.set(20, 5, 20);
    scene.add(pointLight2);

    const gridHelper = new THREE.GridHelper(80, 40, 0x1e3a5f, 0x1e293b);
    gridHelper.position.y = -0.1;
    scene.add(gridHelper);

    const nodesGroup = new THREE.Group();
    scene.add(nodesGroup);
    nodesGroupRef.current = nodesGroup;

    const prModulesGroup = new THREE.Group();
    scene.add(prModulesGroup);
    prModulesGroupRef.current = prModulesGroup;

    addConstellationLines(scene);
    addCentralCore(scene);

    const handleResize = () => {
      if (!containerRef.current || !camera || !renderer) return;
      camera.aspect = containerRef.current.clientWidth / containerRef.current.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [autoRotate]);

  const addConstellationLines = (scene: THREE.Scene) => {
    const lineMaterial = new THREE.LineBasicMaterial({
      color: 0x4338ca,
      transparent: true,
      opacity: 0.3,
    });

    for (let i = 0; i < 20; i++) {
      const startPoint = new THREE.Vector3(
        (Math.random() - 0.5) * 60,
        Math.random() * 20,
        (Math.random() - 0.5) * 60
      );
      const endPoint = new THREE.Vector3(
        (Math.random() - 0.5) * 60,
        Math.random() * 20,
        (Math.random() - 0.5) * 60
      );

      const geometry = new THREE.BufferGeometry().setFromPoints([startPoint, endPoint]);
      const line = new THREE.Line(geometry, lineMaterial);
      scene.add(line);
    }
  };

  const addCentralCore = (scene: THREE.Scene) => {
    const coreGroup = new THREE.Group();

    const coreGeometry = new THREE.IcosahedronGeometry(3, 2);
    const coreMaterial = new THREE.MeshPhongMaterial({
      color: 0x8b5cf6,
      emissive: 0x4338ca,
      transparent: true,
      opacity: 0.8,
      shininess: 100,
    });
    const core = new THREE.Mesh(coreGeometry, coreMaterial);
    core.castShadow = true;
    coreGroup.add(core);

    const wireframeGeometry = new THREE.IcosahedronGeometry(3.2, 1);
    const wireframeMaterial = new THREE.MeshBasicMaterial({
      color: 0xa78bfa,
      wireframe: true,
      transparent: true,
      opacity: 0.4,
    });
    const wireframe = new THREE.Mesh(wireframeGeometry, wireframeMaterial);
    coreGroup.add(wireframe);

    const ringGeometry = new THREE.TorusGeometry(5, 0.05, 16, 100);
    const ringMaterial = new THREE.MeshBasicMaterial({
      color: 0x6366f1,
      transparent: true,
      opacity: 0.6,
    });
    const ring1 = new THREE.Mesh(ringGeometry, ringMaterial);
    ring1.rotation.x = Math.PI / 2;
    coreGroup.add(ring1);

    const ring2 = new THREE.Mesh(ringGeometry, ringMaterial);
    ring2.rotation.x = Math.PI / 4;
    ring2.rotation.y = Math.PI / 4;
    coreGroup.add(ring2);

    coreGroup.position.y = 2;
    coreGroup.userData = { isCore: true };
    scene.add(coreGroup);
  };

  const createKnowledgeNodes = useCallback(() => {
    if (!nodesGroupRef.current || !sceneRef.current) return;

    const group = nodesGroupRef.current;
    while (group.children.length > 0) {
      group.remove(group.children[0]);
    }
    nodeMeshesRef.current.clear();

    const newNodes: KnowledgeNode[] = [];
    const itemsToUse = knowledgeItems.length > 0 ? knowledgeItems : generateSampleKnowledge();

    itemsToUse.forEach((item, index) => {
      const angle = (index / itemsToUse.length) * Math.PI * 2;
      const radius = 10 + Math.random() * 15;
      const height = Math.random() * 15 - 5;

      const position = new THREE.Vector3(
        Math.cos(angle) * radius,
        height,
        Math.sin(angle) * radius
      );

      const node: KnowledgeNode = {
        id: item.id,
        type: item.knowledge_type,
        title: item.title,
        content: item.content,
        confidence: item.confidence_score,
        occurrence: item.occurrence_count,
        tags: item.tags || [],
        position,
      };
      newNodes.push(node);

      const nodeGroup = createNodeMesh(node, index);
      nodeGroup.position.copy(position);
      group.add(nodeGroup);
      nodeMeshesRef.current.set(item.id, nodeGroup.children[0] as THREE.Mesh);
    });

    setNodes(newNodes);
  }, [knowledgeItems]);

  const generateSampleKnowledge = () => {
    const types = ["code_standard", "common_issue", "historical_dispute", "project_context", "best_practice"];
    const titles = [
      "Use TypeScript strict mode",
      "Avoid nested try-catch blocks",
      "API rate limiting discussion",
      "Database connection pooling config",
      "Prefer functional components",
      "Handle null values properly",
      "Authentication flow debate",
      "Cache invalidation strategy",
      "Consistent error formatting",
      "Async/await vs Promises",
      "Component naming conventions",
      "State management approach",
    ];

    return titles.map((title, i) => ({
      id: i + 1,
      knowledge_type: types[i % types.length],
      title,
      content: `This is a knowledge item about ${title.toLowerCase()}. It contains important guidelines for the team.`,
      confidence_score: 0.5 + Math.random() * 0.5,
      occurrence_count: Math.floor(Math.random() * 10) + 1,
      tags: ["sample", "demo"],
    }));
  };

  const createNodeMesh = (node: KnowledgeNode, index: number): THREE.Group => {
    const group = new THREE.Group();

    const color = new THREE.Color(TYPE_COLORS[node.type] || "#6366f1");
    const size = 0.8 + node.confidence * 0.6 + node.occurrence * 0.1;

    const geometryType = node.type === "code_standard" ? "box" :
                       node.type === "historical_dispute" ? "cone" :
                       node.type === "best_practice" ? "dodecahedron" : "sphere";

    let geometry: THREE.BufferGeometry;
    switch (geometryType) {
      case "box":
        geometry = new THREE.BoxGeometry(size, size, size);
        break;
      case "cone":
        geometry = new THREE.ConeGeometry(size / 2, size, 6);
        break;
      case "dodecahedron":
        geometry = new THREE.DodecahedronGeometry(size / 2);
        break;
      default:
        geometry = new THREE.SphereGeometry(size / 2, 16, 16);
    }

    const material = new THREE.MeshPhongMaterial({
      color,
      emissive: color.clone().multiplyScalar(0.3),
      transparent: true,
      opacity: 0.9,
      shininess: 80,
    });

    const mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.userData = { node, index };
    group.add(mesh);

    const ringGeometry = new THREE.RingGeometry(size / 2 + 0.2, size / 2 + 0.3, 32);
    const ringMaterial = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.4,
      side: THREE.DoubleSide,
    });
    const ring = new THREE.Mesh(ringGeometry, ringMaterial);
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = -size / 2 - 0.1;
    group.add(ring);

    const glowGeometry = new THREE.SphereGeometry(size / 2 + 0.3, 16, 16);
    const glowMaterial = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.15,
    });
    const glow = new THREE.Mesh(glowGeometry, glowMaterial);
    group.add(glow);

    return group;
  };

  const addPRModule = useCallback((prData: {
    number: number;
    title: string;
    filesChanged: number;
    additions: number;
    deletions: number;
    matchScore: number;
  }) => {
    if (!prModulesGroupRef.current) return;

    const startPosition = new THREE.Vector3(
      (Math.random() - 0.5) * 40,
      25,
      (Math.random() - 0.5) * 40
    );

    const targetAngle = Math.random() * Math.PI * 2;
    const targetRadius = 8 + Math.random() * 5;
    const targetPosition = new THREE.Vector3(
      Math.cos(targetAngle) * targetRadius,
      2 + Math.random() * 3,
      Math.sin(targetAngle) * targetRadius
    );

    const isMatch = prData.matchScore > 0.7;
    const color = new THREE.Color(isMatch ? 0x22c55e : 0xef4444);

    const newModule: PRModule = {
      id: `pr-${Date.now()}-${Math.random()}`,
      number: prData.number,
      title: prData.title,
      status: "incoming",
      filesChanged: prData.filesChanged,
      additions: prData.additions,
      deletions: prData.deletions,
      matchScore: prData.matchScore,
      startPosition,
      targetPosition,
      currentPosition: startPosition.clone(),
      rotation: new THREE.Euler(0, 0, 0),
      color,
    };

    const moduleGroup = createPRModuleMesh(newModule);
    moduleGroup.position.copy(startPosition);
    prModulesGroupRef.current.add(moduleGroup);
    prMeshesRef.current.set(newModule.id, moduleGroup);

    setPrModules((prev) => [...prev, newModule]);
    setActivePR(newModule);

    animatePRModule(newModule, moduleGroup);
  }, []);

  const createPRModuleMesh = (module: PRModule): THREE.Group => {
    const group = new THREE.Group();

    const boxSize = 1.5 + Math.min(module.filesChanged * 0.1, 2);
    const geometry = new THREE.BoxGeometry(boxSize, boxSize * 0.6, boxSize);

    const material = new THREE.MeshPhongMaterial({
      color: module.color,
      emissive: module.color.clone().multiplyScalar(0.3),
      transparent: true,
      opacity: 0.85,
      shininess: 100,
    });

    const mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.userData = { module };
    group.add(mesh);

    const wireframeGeometry = new THREE.BoxGeometry(boxSize + 0.1, boxSize * 0.6 + 0.1, boxSize + 0.1);
    const wireframeMaterial = new THREE.MeshBasicMaterial({
      color: module.color,
      wireframe: true,
      transparent: true,
      opacity: 0.3,
    });
    const wireframe = new THREE.Mesh(wireframeGeometry, wireframeMaterial);
    group.add(wireframe);

    const edgesGeometry = new THREE.EdgesGeometry(new THREE.BoxGeometry(boxSize, boxSize * 0.6, boxSize));
    const edgesMaterial = new THREE.LineBasicMaterial({
      color: module.color,
      transparent: true,
      opacity: 0.8,
    });
    const edges = new THREE.LineSegments(edgesGeometry, edgesMaterial);
    group.add(edges);

    return group;
  };

  const animatePRModule = (module: PRModule, meshGroup: THREE.Group) => {
    let progress = 0;
    const duration = 3000;
    const startTime = Date.now();

    const animate = () => {
      const elapsed = Date.now() - startTime;
      progress = Math.min(elapsed / duration, 1);

      const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);
      const easedProgress = easeOutCubic(progress);

      const position = new THREE.Vector3().lerpVectors(
        module.startPosition,
        module.targetPosition,
        easedProgress
      );

      const wobble = Math.sin(progress * Math.PI * 4) * (1 - progress) * 2;
      position.y += wobble;

      meshGroup.position.copy(position);
      meshGroup.rotation.y = progress * Math.PI * 4;
      meshGroup.rotation.x = Math.sin(progress * Math.PI * 2) * 0.5;

      const scale = 1 + Math.sin(progress * Math.PI) * 0.2;
      meshGroup.scale.setScalar(scale);

      if (progress < 1) {
        if (progress < 0.3) {
          setPrModules((prev) =>
            prev.map((m) => (m.id === module.id ? { ...m, status: "snapping" } : m))
          );
        } else if (progress >= 0.9) {
          const finalStatus = module.matchScore > 0.7 ? "snapped" : "rejected";
          setPrModules((prev) =>
            prev.map((m) => (m.id === module.id ? { ...m, status: finalStatus } : m))
          );
        }
        requestAnimationFrame(animate);
      }
    };

    animate();
  };

  const animate = useCallback(() => {
    if (!sceneRef.current || !cameraRef.current || !rendererRef.current || !controlsRef.current) {
      return;
    }

    const scene = sceneRef.current;
    const renderer = rendererRef.current;
    const controls = controlsRef.current;

    const animateLoop = () => {
      animationFrameRef.current = requestAnimationFrame(animateLoop);

      if (isAnimating) {
        scene.traverse((child) => {
          if (child instanceof THREE.Group && child.userData.isCore) {
            child.rotation.y += 0.002;
            child.children.forEach((c, i) => {
              if (i > 1) {
                c.rotation.z += 0.003 * (i % 2 === 0 ? 1 : -1);
              }
            });
          }

          if (child instanceof THREE.Group && nodesGroupRef.current?.children.includes(child)) {
            child.rotation.y += 0.003;
            const originalY = child.position.y;
            child.position.y = originalY + Math.sin(Date.now() * 0.001 + child.position.x) * 0.05;
          }
        });
      }

      controls.update();
      renderer.render(scene, cameraRef.current!);
    };

    animateLoop();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isAnimating]);

  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (!containerRef.current || !cameraRef.current || !sceneRef.current) return;

      const rect = containerRef.current.getBoundingClientRect();
      mouseRef.current.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouseRef.current.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycasterRef.current.setFromCamera(mouseRef.current, cameraRef.current);

      const intersects: THREE.Intersection[] = [];

      nodeMeshesRef.current.forEach((mesh) => {
        const meshIntersects = raycasterRef.current.intersectObject(mesh);
        intersects.push(...meshIntersects);
      });

      if (intersects.length > 0) {
        const firstIntersect = intersects[0];
        const nodeData = (firstIntersect.object as THREE.Mesh).userData.node as KnowledgeNode;
        if (nodeData) {
          setSelectedNode(nodeData);
          onNodeSelect?.(nodeData);
        }
      } else {
        setSelectedNode(null);
      }
    },
    [onNodeSelect]
  );

  const resetCamera = () => {
    if (cameraRef.current && controlsRef.current) {
      cameraRef.current.position.set(25, 20, 25);
      controlsRef.current.target.set(0, 2, 0);
      controlsRef.current.update();
    }
  };

  const zoomIn = () => {
    if (cameraRef.current) {
      const direction = new THREE.Vector3();
      cameraRef.current.getWorldDirection(direction);
      cameraRef.current.position.addScaledVector(direction, 5);
    }
  };

  const zoomOut = () => {
    if (cameraRef.current) {
      const direction = new THREE.Vector3();
      cameraRef.current.getWorldDirection(direction);
      cameraRef.current.position.addScaledVector(direction, -5);
    }
  };

  const triggerSamplePR = () => {
    const samplePRs = [
      { title: "Add user authentication", filesChanged: 5, additions: 120, deletions: 30, matchScore: 0.85 },
      { title: "Fix API rate limiting", filesChanged: 3, additions: 45, deletions: 12, matchScore: 0.92 },
      { title: "Refactor database queries", filesChanged: 8, additions: 200, deletions: 80, matchScore: 0.65 },
      { title: "Update dependency versions", filesChanged: 2, additions: 10, deletions: 10, matchScore: 0.45 },
    ];
    const randomPR = samplePRs[Math.floor(Math.random() * samplePRs.length)];
    addPRModule({
      ...randomPR,
      number: Math.floor(Math.random() * 1000) + 100,
    });
  };

  useEffect(() => {
    const cleanup = initScene();
    return () => {
      cleanup?.();
      if (rendererRef.current && containerRef.current) {
        containerRef.current.removeChild(rendererRef.current.domElement);
        rendererRef.current.dispose();
      }
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [initScene]);

  useEffect(() => {
    if (nodesGroupRef.current) {
      createKnowledgeNodes();
    }
  }, [createKnowledgeNodes, knowledgeItems]);

  useEffect(() => {
    if (sceneRef.current) {
      const cleanup = animate();
      return cleanup;
    }
  }, [animate, isAnimating]);

  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.autoRotate = autoRotate;
    }
  }, [autoRotate]);

  return (
    <div className="relative w-full h-full">
      <div
        ref={containerRef}
        onClick={handleClick}
        className="w-full h-full cursor-crosshair"
      />

      <div className="absolute top-4 left-4 flex flex-col gap-2">
        <div className="bg-slate-900/90 backdrop-blur-sm rounded-lg p-3 border border-slate-700">
          <div className="text-xs text-slate-400 mb-2 flex items-center gap-1">
            <Layers className="h-3 w-3" />
            Controls
          </div>
          <div className="flex flex-col gap-2">
            <div className="flex gap-2">
              <button
                onClick={() => setIsAnimating(!isAnimating)}
                className={`p-2 rounded-lg text-xs flex items-center gap-1 ${
                  isAnimating
                    ? "bg-purple-600 text-white"
                    : "bg-slate-800 text-slate-400 hover:text-white"
                }`}
              >
                {isAnimating ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                {isAnimating ? "Pause" : "Play"}
              </button>
              <button
                onClick={() => setAutoRotate(!autoRotate)}
                className={`p-2 rounded-lg text-xs ${
                  autoRotate
                    ? "bg-purple-600 text-white"
                    : "bg-slate-800 text-slate-400 hover:text-white"
                }`}
              >
                Rotate: {autoRotate ? "ON" : "OFF"}
              </button>
            </div>
            <div className="flex gap-2">
              <button
                onClick={zoomIn}
                className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:text-white"
              >
                <ZoomIn className="h-3 w-3" />
              </button>
              <button
                onClick={zoomOut}
                className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:text-white"
              >
                <ZoomOut className="h-3 w-3" />
              </button>
              <button
                onClick={resetCamera}
                className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:text-white"
              >
                <RotateCcw className="h-3 w-3" />
              </button>
            </div>
          </div>
        </div>

        <button
          onClick={triggerSamplePR}
          className="bg-gradient-to-r from-purple-600 to-cyan-600 hover:from-purple-500 hover:to-cyan-500 text-white px-4 py-2.5 rounded-lg text-sm font-medium flex items-center gap-2 shadow-lg shadow-purple-900/50"
        >
          <Box className="h-4 w-4" />
          Simulate PR Webhook
        </button>
      </div>

      <div className="absolute top-4 right-4 bg-slate-900/90 backdrop-blur-sm rounded-lg p-3 border border-slate-700">
        <div className="text-xs text-slate-400 mb-2">Knowledge Types</div>
        <div className="space-y-1.5">
          {Object.entries(TYPE_COLORS).map(([type, color]) => (
            <div key={type} className="flex items-center gap-2 text-xs">
              <div
                className="w-3 h-3 rounded"
                style={{ backgroundColor: color }}
              />
              <span className="text-slate-300">
                {TYPE_ICONS[type]} {type.replace("_", " ")}
              </span>
            </div>
          ))}
        </div>
      </div>

      {activePR && (
        <div className="absolute bottom-4 left-4 bg-slate-900/90 backdrop-blur-sm rounded-lg p-4 border border-slate-700 max-w-sm">
          <div className="flex items-center gap-2 mb-2">
            <Box className={`h-4 w-4 ${activePR.status === "snapped" ? "text-green-400" : activePR.status === "rejected" ? "text-red-400" : "text-yellow-400"}`} />
            <span className="text-sm font-medium">
              PR #{activePR.number}: {activePR.title}
            </span>
          </div>
          <div className="text-xs text-slate-400 space-y-1">
            <div className="flex justify-between">
              <span>Status:</span>
              <span
                className={`font-medium ${
                  activePR.status === "snapped"
                    ? "text-green-400"
                    : activePR.status === "rejected"
                    ? "text-red-400"
                    : "text-yellow-400"
                }`}
              >
                {activePR.status === "incoming"
                  ? "📥 Incoming"
                  : activePR.status === "snapping"
                  ? "🔧 Snapping (榫卯拼合中...)"
                  : activePR.status === "snapped"
                  ? "✅ Snapped - Matches architecture"
                  : "❌ Rejected - Conflicts detected"}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Match Score:</span>
              <span className={activePR.matchScore > 0.7 ? "text-green-400" : "text-red-400"}>
                {(activePR.matchScore * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span>Files Changed:</span>
              <span>{activePR.filesChanged}</span>
            </div>
            <div className="flex justify-between">
              <span>Lines:</span>
              <span>
                <span className="text-green-400">+{activePR.additions}</span> /{" "}
                <span className="text-red-400">-{activePR.deletions}</span>
              </span>
            </div>
          </div>
        </div>
      )}

      {selectedNode && (
        <div className="absolute bottom-4 right-4 bg-slate-900/90 backdrop-blur-sm rounded-lg p-4 border border-slate-700 max-w-xs">
          <div className="flex items-center gap-2 mb-2">
            <Info className="h-4 w-4 text-purple-400" />
            <span className="text-sm font-medium">{selectedNode.title}</span>
          </div>
          <div className="text-xs text-slate-400 space-y-2">
            <div className="flex items-center gap-1">
              <span
                className="px-2 py-0.5 rounded text-xs"
                style={{
                  backgroundColor: TYPE_COLORS[selectedNode.type] + "33",
                  color: TYPE_COLORS[selectedNode.type],
                }}
              >
                {TYPE_ICONS[selectedNode.type]} {selectedNode.type.replace("_", " ")}
              </span>
            </div>
            <p className="line-clamp-3">{selectedNode.content}</p>
            <div className="flex gap-4">
              <div>
                <span className="text-slate-500">Confidence:</span>
                <span className="ml-1 text-white">
                  {(selectedNode.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <div>
                <span className="text-slate-500">Occurrences:</span>
                <span className="ml-1 text-white">{selectedNode.occurrence}</span>
              </div>
            </div>
            {selectedNode.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {selectedNode.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-1.5 py-0.5 bg-slate-800 rounded text-slate-400"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none">
        {prModules.length === 0 && (
          <div className="text-center text-slate-500">
            <Box className="h-12 w-12 mx-auto mb-2 opacity-30" />
            <p className="text-sm">Click nodes to inspect</p>
            <p className="text-xs mt-1">Use "Simulate PR Webhook" to see 榫卯 animation</p>
          </div>
        )}
      </div>
    </div>
  );
}
