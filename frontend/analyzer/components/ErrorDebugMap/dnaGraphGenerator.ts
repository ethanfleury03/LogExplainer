import type { GraphNode, GraphLink, CallGraphData } from './dummyCallGraph';

const MODULES = ['Gymea', 'Kareela', 'PDL', 'Core', 'Utils', 'Parser', 'Renderer'];
const GROUPS = ['gymea', 'kareela', 'pdl', 'unknown'];
const FUNCTION_PREFIXES = ['process', 'handle', 'parse', 'render', 'validate', 'transform', 'execute', 'initialize', 'finalize', 'update', 'create', 'destroy'];

function randomChoice<T>(arr: T[], randomFn: () => number = Math.random): T {
  return arr[Math.floor(randomFn() * arr.length)];
}

function randomInt(min: number, max: number, randomFn: () => number = Math.random): number {
  return Math.floor(randomFn() * (max - min + 1)) + min;
}

function generateFunctionName(module: string, index: number, randomFn: () => number): string {
  const prefix = randomChoice(FUNCTION_PREFIXES, randomFn);
  const suffix = randomChoice(['Data', 'Request', 'Response', 'Event', 'Message', 'Config', 'State', 'Result'], randomFn);
  return `${prefix}${suffix}${index}`;
}

function generateQualName(module: string, className: string | null, funcName: string): string {
  if (className) {
    return `${module}.${className}.${funcName}`;
  }
  return `${module}.${funcName}`;
}

function generateFilePath(module: string, randomFn: () => number): string {
  return `/opt/memjet/${module}/${randomChoice(['src', 'lib', 'core', 'utils'], randomFn)}/${randomChoice(['main', 'handler', 'processor', 'parser'], randomFn)}.py`;
}

interface DnaGraphOptions {
  strands?: number;
  nodesPerStrand?: number;
  radius?: number;
  pitch?: number;
  rungEvery?: number;
  extraCrossLinks?: number;
  seed?: number;
}

export function generateDnaGraph(options: DnaGraphOptions = {}): CallGraphData {
  const {
    strands = 2,
    nodesPerStrand = 120,
    radius = 60,
    pitch = 3.2,
    rungEvery = 3,
    extraCrossLinks = 0.05,
    seed,
  } = options;

  // Seeded random function
  let seedValue = seed !== undefined ? seed : Math.floor(Math.random() * 1000000);
  const seededRandom = () => {
    seedValue = (seedValue * 9301 + 49297) % 233280;
    return seedValue / 233280;
  };
  
  const random = seed !== undefined ? seededRandom : Math.random;

  const nodes: (GraphNode & { x?: number; y?: number; z?: number; degree?: number })[] = [];
  const links: GraphLink[] = [];
  const nodeMap = new Map<string, typeof nodes[0]>();

  // Generate nodes in DNA helix structure
  let nodeIndex = 0;
  
  for (let strandIdx = 0; strandIdx < strands; strandIdx++) {
    for (let i = 0; i < nodesPerStrand; i++) {
      const angle = i * 0.35 + (strandIdx * Math.PI / strands);
      const y = (i - nodesPerStrand / 2) * pitch;
      
      // Calculate position in helix
      const x = radius * Math.cos(angle);
      const z = radius * Math.sin(angle);
      
      // Add slight jitter for realism (but keep deterministic with seed)
      const jitterX = (random() - 0.5) * 2;
      const jitterY = (random() - 0.5) * 1;
      const jitterZ = (random() - 0.5) * 2;
      
      const group = GROUPS[strandIdx % GROUPS.length];
      const module = randomChoice(MODULES, random);
      const hasClass = random() > 0.5;
      const className = hasClass ? `${module}Class${i % 10}` : null;
      const funcName = generateFunctionName(module, nodeIndex, random);
      const qualname = generateQualName(module, className, funcName);
      const file = generateFilePath(module, random);
      const line = randomInt(1, 5000, random);

      const node: typeof nodes[0] = {
        id: `node_${nodeIndex}`,
        name: funcName,
        qualname,
        file,
        line,
        group,
        x: x + jitterX,
        y: y + jitterY,
        z: z + jitterZ,
        degree: 0,
      };

      nodes.push(node);
      nodeMap.set(node.id, node);
      nodeIndex++;
    }
  }

  // Create links: sequential along each strand
  for (let strandIdx = 0; strandIdx < strands; strandIdx++) {
    const startIdx = strandIdx * nodesPerStrand;
    for (let i = 0; i < nodesPerStrand - 1; i++) {
      const sourceIdx = startIdx + i;
      const targetIdx = startIdx + i + 1;
      links.push({ 
        source: nodes[sourceIdx].id, 
        target: nodes[targetIdx].id 
      });
      nodes[sourceIdx].degree = (nodes[sourceIdx].degree || 0) + 1;
      nodes[targetIdx].degree = (nodes[targetIdx].degree || 0) + 1;
    }
  }

  // Create rungs (cross-links between strands) every rungEvery nodes
  if (strands >= 2) {
    for (let i = 0; i < nodesPerStrand; i += rungEvery) {
      for (let s1 = 0; s1 < strands; s1++) {
        for (let s2 = s1 + 1; s2 < strands; s2++) {
          const idx1 = s1 * nodesPerStrand + i;
          const idx2 = s2 * nodesPerStrand + i;
          if (idx1 < nodes.length && idx2 < nodes.length) {
            links.push({ 
              source: nodes[idx1].id, 
              target: nodes[idx2].id 
            });
            nodes[idx1].degree = (nodes[idx1].degree || 0) + 1;
            nodes[idx2].degree = (nodes[idx2].degree || 0) + 1;
          }
        }
      }
    }
  }

  // Add sparse extra cross-links for realism
  const numExtraLinks = Math.floor(links.length * extraCrossLinks);
  const linkSet = new Set<string>();
  links.forEach(link => {
    linkSet.add(`${link.source}-${link.target}`);
    linkSet.add(`${link.target}-${link.source}`);
  });

  for (let i = 0; i < numExtraLinks; i++) {
    let attempts = 0;
    while (attempts < 100) {
      const sourceNode = nodes[Math.floor(random() * nodes.length)];
      const targetNode = nodes[Math.floor(random() * nodes.length)];
      
      if (sourceNode.id === targetNode.id) {
        attempts++;
        continue;
      }

      const linkKey = `${sourceNode.id}-${targetNode.id}`;
      const reverseKey = `${targetNode.id}-${sourceNode.id}`;
      
      if (!linkSet.has(linkKey) && !linkSet.has(reverseKey)) {
        links.push({ source: sourceNode.id, target: targetNode.id });
        linkSet.add(linkKey);
        sourceNode.degree = (sourceNode.degree || 0) + 1;
        targetNode.degree = (targetNode.degree || 0) + 1;
        break;
      }
      attempts++;
    }
  }

  // Remove position and degree from final nodes (they're added by force simulation)
  const finalNodes: GraphNode[] = nodes.map(({ x, y, z, degree, ...node }) => node);

  return { nodes: finalNodes, links };
}


