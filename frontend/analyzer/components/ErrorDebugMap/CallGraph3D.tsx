'use client';

import { useMemo, useRef, useCallback, useImperativeHandle, forwardRef, useEffect } from 'react';
import dynamic from 'next/dynamic';
import type { GraphNode, GraphLink } from './dummyCallGraph';

// We'll access d3-force-3d through the graph instance if needed

// Dynamically import ForceGraph3D with SSR disabled
const ForceGraph3D = dynamic(() => import('react-force-graph-3d'), {
  ssr: false,
  loading: () => <div className="flex items-center justify-center h-full">Loading 3D graph...</div>,
});

interface CallGraph3DProps {
  nodes: GraphNode[];
  links: GraphLink[];
  highlightNodeIds: Set<string>;
  onNodeClick?: (node: GraphNode | null) => void;
  showLabels?: boolean;
}

export interface CallGraph3DRef {
  resetCamera: () => void;
}

export const CallGraph3D = forwardRef<CallGraph3DRef, CallGraph3DProps>(
  ({ nodes, links, highlightNodeIds, onNodeClick, showLabels = false }, ref) => {
    const graphRef = useRef<any>();
    const hasCenteredRef = useRef(false);

    // Compute node colors and opacities based on highlighting
    const nodeData = useMemo(() => {
      return nodes.map((node) => {
        const isHighlighted = highlightNodeIds.has(node.id);
        
        // Find neighbors (1-hop)
        const neighborIds = new Set<string>();
        links.forEach((link) => {
          if (link.source === node.id) neighborIds.add(link.target as string);
          if (link.target === node.id) neighborIds.add(link.source as string);
        });
        const isNeighbor = Array.from(neighborIds).some((id) => highlightNodeIds.has(id));
        
        let color: string;
        let opacity: number;
        
        if (isHighlighted) {
          color = '#3b82f6'; // blue
          opacity = 1.0;
        } else if (isNeighbor && highlightNodeIds.size > 0) {
          color = '#60a5fa'; // lighter blue
          opacity = 0.8;
        } else if (highlightNodeIds.size > 0) {
          color = '#9ca3af'; // gray
          opacity = 0.2;
        } else {
          color = '#9ca3af'; // gray
          opacity = 0.6;
        }

        return {
          ...node,
          color,
          opacity,
        };
      });
    }, [nodes, links, highlightNodeIds]);

    // Compute link colors and opacities
    const linkData = useMemo(() => {
      return links.map((link) => {
        const sourceHighlighted = highlightNodeIds.has(link.source as string);
        const targetHighlighted = highlightNodeIds.has(link.target as string);
        const isHighlighted = sourceHighlighted || targetHighlighted;
        
        return {
          ...link,
          color: isHighlighted ? '#3b82f6' : '#6b7280',
          opacity: isHighlighted ? 0.6 : highlightNodeIds.size > 0 ? 0.1 : 0.3,
        };
      });
    }, [links, highlightNodeIds]);

    const handleNodeClick = useCallback(
      (node: any) => {
        const graphNode = nodes.find((n) => n.id === node.id);
        if (graphNode) {
          onNodeClick?.(graphNode);
          
          // Center camera on node
          if (graphRef.current) {
            const distance = 200;
            const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);
            
            graphRef.current.cameraPosition(
              {
                x: node.x * distRatio,
                y: node.y * distRatio,
                z: node.z * distRatio,
              },
              node,
              3000 // transition duration
            );
          }
        }
      },
      [nodes, onNodeClick]
    );

    const handleNodeHover = useCallback((node: any) => {
      // Tooltip is handled via nodeLabel prop
    }, []);

    // Center camera on graph - use zoomToFit which handles everything
    const centerCameraOnGraph = useCallback(() => {
      if (!graphRef.current) return;

      try {
        const graphData = graphRef.current.graphData();
        const nodesWithPos = graphData?.nodes?.filter((n: any) => 
          n.x !== undefined && n.y !== undefined && n.z !== undefined
        ) || [];
        
        if (nodesWithPos.length > 0) {
          // Calculate center of mass
          let sumX = 0, sumY = 0, sumZ = 0;
          nodesWithPos.forEach((node: any) => {
            sumX += node.x;
            sumY += node.y;
            sumZ += node.z;
          });
          const centerX = sumX / nodesWithPos.length;
          const centerY = sumY / nodesWithPos.length;
          const centerZ = sumZ / nodesWithPos.length;
          
          // Translate all nodes so center of mass is at origin
          nodesWithPos.forEach((node: any) => {
            node.x -= centerX;
            node.y -= centerY;
            node.z -= centerZ;
          });
          
          // Update the graph with centered nodes
          graphRef.current.graphData(graphData);
          
          // Calculate bounding box to determine appropriate camera distance
          let minX = Infinity, maxX = -Infinity;
          let minY = Infinity, maxY = -Infinity;
          let minZ = Infinity, maxZ = -Infinity;
          
          nodesWithPos.forEach((node: any) => {
            minX = Math.min(minX, node.x);
            maxX = Math.max(maxX, node.x);
            minY = Math.min(minY, node.y);
            maxY = Math.max(maxY, node.y);
            minZ = Math.min(minZ, node.z);
            maxZ = Math.max(maxZ, node.z);
          });
          
          const width = maxX - minX;
          const height = maxY - minY;
          const depth = maxZ - minZ;
          const maxDim = Math.max(width, height, depth);
          
          // Position camera to look at origin (0,0,0) from a good distance
          // Use a distance that fits the graph nicely
          const distance = Math.max(maxDim * 1.5, 400);
          
          // Position camera at a good angle looking at origin
          graphRef.current.cameraPosition(
            { x: distance * 0.7, y: distance * 0.5, z: distance * 0.7 },
            { x: 0, y: 0, z: 0 },
            1000
          );
        } else {
          // Fallback: center at origin with good distance
          graphRef.current.cameraPosition(
            { x: 0, y: 0, z: 500 },
            { x: 0, y: 0, z: 0 },
            1000
          );
        }
        hasCenteredRef.current = true;
      } catch (e) {
        // Fallback: center at origin with good distance
        if (graphRef.current) {
          graphRef.current.cameraPosition(
            { x: 0, y: 0, z: 500 },
            { x: 0, y: 0, z: 0 },
            1000
          );
        }
        hasCenteredRef.current = true;
      }
    }, []);

    // Auto-center camera when graph stabilizes
    const handleEngineStop = useCallback(() => {
      // Wait a bit then center - need nodes to have settled positions
      setTimeout(() => {
        if (graphRef.current) {
          const graphData = graphRef.current.graphData();
          const nodesWithPos = graphData?.nodes?.filter((n: any) => 
            n.x !== undefined && n.y !== undefined && n.z !== undefined
          ) || [];
          
          if (nodesWithPos.length > 0) {
            // Calculate center of mass
            let sumX = 0, sumY = 0, sumZ = 0;
            nodesWithPos.forEach((node: any) => {
              sumX += node.x;
              sumY += node.y;
              sumZ += node.z;
            });
            const centerX = sumX / nodesWithPos.length;
            const centerY = sumY / nodesWithPos.length;
            const centerZ = sumZ / nodesWithPos.length;
            
            // Translate all nodes so center of mass is at origin
            nodesWithPos.forEach((node: any) => {
              node.x -= centerX;
              node.y -= centerY;
              node.z -= centerZ;
            });
            
            // Update the graph with centered nodes
            graphRef.current.graphData(graphData);
            
            // Calculate bounding box to determine appropriate camera distance
            let minX = Infinity, maxX = -Infinity;
            let minY = Infinity, maxY = -Infinity;
            let minZ = Infinity, maxZ = -Infinity;
            
            nodesWithPos.forEach((node: any) => {
              minX = Math.min(minX, node.x);
              maxX = Math.max(maxX, node.x);
              minY = Math.min(minY, node.y);
              maxY = Math.max(maxY, node.y);
              minZ = Math.min(minZ, node.z);
              maxZ = Math.max(maxZ, node.z);
            });
            
            const width = maxX - minX;
            const height = maxY - minY;
            const depth = maxZ - minZ;
            const maxDim = Math.max(width, height, depth);
            
            // Position camera to look at origin (0,0,0) from a good distance
            // Use a distance that fits the graph nicely
            const distance = Math.max(maxDim * 1.5, 400);
            
            // Position camera at a good angle looking at origin
            graphRef.current.cameraPosition(
              { x: distance * 0.7, y: distance * 0.5, z: distance * 0.7 },
              { x: 0, y: 0, z: 0 },
              1000
            );
            hasCenteredRef.current = true;
          }
        }
      }, 500);
    }, []);

    // Add centering force to keep nodes at origin
    useEffect(() => {
      if (graphRef.current && nodes.length > 0) {
        // Add a weak centering force that pulls nodes toward origin
        graphRef.current.d3Force('center', (alpha: number) => {
          const nodes = graphRef.current?.graphData()?.nodes || [];
          nodes.forEach((node: any) => {
            if (node.x !== undefined && node.y !== undefined && node.z !== undefined) {
              // Weak force toward origin
              const strength = 0.05 * alpha;
              node.vx = (node.vx || 0) - node.x * strength;
              node.vy = (node.vy || 0) - node.y * strength;
              node.vz = (node.vz || 0) - node.z * strength;
            }
          });
        });
      }
    }, [nodes.length]);

    // Center camera when nodes/links change (reset flag on data change)
    useEffect(() => {
      hasCenteredRef.current = false;
      if (nodes.length > 0) {
        // Multiple attempts with increasing delays to ensure graph has settled
        const timers = [
          setTimeout(() => {
            if (graphRef.current) centerCameraOnGraph();
          }, 800),
          setTimeout(() => {
            if (graphRef.current) centerCameraOnGraph();
          }, 1500),
          setTimeout(() => {
            if (graphRef.current) centerCameraOnGraph();
          }, 2500),
        ];
        return () => timers.forEach(timer => clearTimeout(timer));
      }
    }, [nodes.length, links.length, centerCameraOnGraph]);

    // Expose camera reset function via ref
    useImperativeHandle(ref, () => ({
      resetCamera: () => {
        centerCameraOnGraph();
      },
    }));

    return (
      <div className="absolute inset-0 w-full h-full force-graph-container">
        <ForceGraph3D
          ref={graphRef}
          graphData={{ nodes: nodeData, links: linkData }}
          nodeLabel={(node: any) => {
            const graphNode = nodes.find((n) => n.id === node.id);
            if (graphNode) {
              return `${graphNode.name}\n${graphNode.file}:${graphNode.line}`;
            }
            return '';
          }}
          nodeColor={(node: any) => node.color || '#9ca3af'}
          nodeOpacity={(node: any) => node.opacity || 0.6}
          linkColor={(link: any) => link.color || '#6b7280'}
          linkOpacity={(link: any) => link.opacity || 0.3}
          linkWidth={1}
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={1}
          onNodeClick={handleNodeClick}
          onNodeHover={handleNodeHover}
          enableNodeDrag={true}
          cooldownTicks={100}
          onEngineStop={handleEngineStop}
        />
      </div>
    );
  }
);

CallGraph3D.displayName = 'CallGraph3D';
