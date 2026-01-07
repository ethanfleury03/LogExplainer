export interface GraphNode {
  id: string;
  name: string;
  qualname: string;
  file: string;
  line: number;
  group: string;
}

export interface GraphLink {
  source: string;
  target: string;
}

export interface CallGraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

const MODULES = ['Gymea', 'Kareela', 'PDL', 'Core', 'Utils', 'Parser', 'Renderer'];
const GROUPS = ['gymea', 'kareela', 'pdl', 'unknown'];
const FUNCTION_PREFIXES = ['process', 'handle', 'parse', 'render', 'validate', 'transform', 'execute', 'initialize', 'finalize', 'update', 'create', 'destroy'];

function randomChoice<T>(arr: T[], randomFn: () => number = Math.random): T {
  return arr[Math.floor(randomFn() * arr.length)];
}

function randomInt(min: number, max: number, randomFn: () => number = Math.random): number {
  return Math.floor(randomFn() * (max - min + 1)) + min;
}

function generateFunctionName(module: string, index: number): string {
  const prefix = randomChoice(FUNCTION_PREFIXES);
  const suffix = randomChoice(['Data', 'Request', 'Response', 'Event', 'Message', 'Config', 'State', 'Result']);
  return `${prefix}${suffix}${index}`;
}

function generateQualName(module: string, className: string | null, funcName: string): string {
  if (className) {
    return `${module}.${className}.${funcName}`;
  }
  return `${module}.${funcName}`;
}

function generateFilePath(module: string): string {
  return `/opt/memjet/${module}/${randomChoice(['src', 'lib', 'core', 'utils'])}/${randomChoice(['main', 'handler', 'processor', 'parser'])}.py`;
}

export function generateDummyCallGraph(seed?: number): CallGraphData {
  // Seeded random function (doesn't override Math.random)
  let seedValue = seed !== undefined ? seed : Math.floor(Math.random() * 1000000);
  const seededRandom = () => {
    seedValue = (seedValue * 9301 + 49297) % 233280;
    return seedValue / 233280;
  };
  
  // Use seeded random if seed provided, otherwise use Math.random
  const random = seed !== undefined ? seededRandom : Math.random;

  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];
  const nodeMap = new Map<string, GraphNode>();

  // Generate ~250 nodes
  const numNodes = 250;
  const nodesPerGroup = Math.floor(numNodes / GROUPS.length);

  for (let i = 0; i < numNodes; i++) {
    const group = GROUPS[Math.floor(i / nodesPerGroup) % GROUPS.length];
    const module = randomChoice(MODULES, random);
    const hasClass = random() > 0.5;
    const className = hasClass ? `${module}Class${i % 10}` : null;
    const funcName = generateFunctionName(module, i);
    const qualname = generateQualName(module, className, funcName);
    const file = generateFilePath(module);
    const line = randomInt(1, 5000, random);

    const node: GraphNode = {
      id: `node_${i}`,
      name: funcName,
      qualname,
      file,
      line,
      group,
    };

    nodes.push(node);
    nodeMap.set(node.id, node);
  }

  // Generate ~350 links
  // Strategy: Create a mostly connected graph with some clusters
  const numLinks = 350;
  const linkSet = new Set<string>();

  // First, create a spanning tree to ensure connectivity
  for (let i = 1; i < nodes.length; i++) {
    const source = nodes[Math.floor(random() * i)].id;
    const target = nodes[i].id;
    const linkKey = `${source}-${target}`;
    if (!linkSet.has(linkKey)) {
      links.push({ source, target });
      linkSet.add(linkKey);
    }
  }

  // Add remaining links randomly, with preference for same-group connections
  const remainingLinks = numLinks - links.length;
  for (let i = 0; i < remainingLinks; i++) {
    let attempts = 0;
    while (attempts < 100) {
      const sourceNode = randomChoice(nodes, random);
      const targetNode = randomChoice(nodes, random);
      
      if (sourceNode.id === targetNode.id) {
        attempts++;
        continue;
      }

      const linkKey = `${sourceNode.id}-${targetNode.id}`;
      const reverseKey = `${targetNode.id}-${sourceNode.id}`;
      
      if (!linkSet.has(linkKey) && !linkSet.has(reverseKey)) {
        // Prefer same-group connections (70% chance)
        if (sourceNode.group === targetNode.group || random() > 0.3) {
          links.push({ source: sourceNode.id, target: targetNode.id });
          linkSet.add(linkKey);
          break;
        }
      }
      attempts++;
    }
  }

  return { nodes, links };
}

