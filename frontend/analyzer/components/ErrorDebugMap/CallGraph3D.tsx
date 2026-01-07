'use client';

import { useMemo, useRef, useCallback, useImperativeHandle, forwardRef, useEffect, useState } from 'react';
import ForceGraph3D, { type ForceGraphMethods } from 'react-force-graph-3d';
import * as THREE from 'three';
import type { GraphNode, GraphLink } from './dummyCallGraph';

interface CallGraph3DProps {
  nodes: GraphNode[];
  links: GraphLink[];
  highlightNodeIds: Set<string>;
  activeNodeId?: string | null; // Node that is currently focused (clicked highlighted node)
  onNodeClick?: (node: GraphNode | null) => void;
  showLabels?: boolean;
  spacingScale?: number; // Optional spacing multiplier
}

export interface CallGraph3DRef {
  resetCamera: () => void;
}

export const CallGraph3D = forwardRef<CallGraph3DRef, CallGraph3DProps>(
  ({ nodes, links, highlightNodeIds, activeNodeId = null, onNodeClick, showLabels = false, spacingScale = 5.0 }, ref) => {
    const graphRef = useRef<ForceGraphMethods | null>(null);
    const hasCenteredRef = useRef(false);
    const hasLoggedEngineStart = useRef(false);
    const [isFrozen, setIsFrozen] = useState(false);
    const previousDataHash = useRef<string>('');

    // Calculate node degrees for size scaling
    const nodeDegrees = useMemo(() => {
      const degrees = new Map<string, number>();
      nodes.forEach(node => degrees.set(node.id, 0));
      links.forEach(link => {
        const source = typeof link.source === 'string' ? link.source : link.source.id;
        const target = typeof link.target === 'string' ? link.target : link.target.id;
        degrees.set(source, (degrees.get(source) || 0) + 1);
        degrees.set(target, (degrees.get(target) || 0) + 1);
      });
      return degrees;
    }, [nodes, links]);

    // Create THREE.js sphere nodes with glow effect
    // Note: node here is from nodeData (with color/opacity already computed)
    const makeNodeObject = useCallback((node: any) => {
      const degree = nodeDegrees.get(node.id) || 1;
      const isHighlighted = highlightNodeIds.has(node.id);
      
      // Make highlighted nodes larger
      const baseRadius = isHighlighted ? 3.5 : 2.3;
      const radius = baseRadius + Math.min(3, degree * 0.35);
      
      const geometry = new THREE.SphereGeometry(radius, 16, 16);
      
      // Use node color if available, otherwise default
      const baseColor = node.color || (isHighlighted ? '#2563eb' : '#4b5563');
      
      const material = new THREE.MeshStandardMaterial({
        color: baseColor,
        emissive: baseColor,
        emissiveIntensity: isHighlighted ? 0.8 : 0.3, // Brighter glow for highlighted
        roughness: 0.4,
        metalness: 0.1,
        transparent: true,
        opacity: node.opacity !== undefined ? node.opacity : (isHighlighted ? 1.0 : 0.9),
      });
      
      const mesh = new THREE.Mesh(geometry, material);
      mesh.castShadow = false;
      mesh.receiveShadow = false;
      
      // Store node id for potential updates
      (mesh as any).__nodeId = node.id;
      
      return mesh;
    }, [nodeDegrees, highlightNodeIds, activeNodeId]);

    // Helper to get node ID from source/target (handles both string and object)
    const getNodeId = useCallback((x: any): string => {
      return String(x?.id ?? x);
    }, []);

    // Compute neighbor node IDs (nodes connected to activeNodeId) - must be before nodeData
    const neighborIds = useMemo(() => {
      if (!activeNodeId) return new Set<string>();
      
      const n = new Set<string>();
      for (const l of links) {
        const s = getNodeId((l as any).source);
        const t = getNodeId((l as any).target);
        if (s === activeNodeId) n.add(t);
        if (t === activeNodeId) n.add(s);
      }
      return n;
    }, [activeNodeId, links, getNodeId]);

    // Compute node colors and opacities based on highlighting and active focus
    const nodeData = useMemo(() => {
      return nodes.map((node) => {
        const nodeId = String(node.id);
        const isHighlighted = highlightNodeIds.has(nodeId);
        const isActive = activeNodeId === nodeId;
        const isNeighbor = neighborIds.has(nodeId);
        
        let color: string;
        let opacity: number;
        
        if (isActive) {
          // Focused highlighted node (clicked)
          color = '#1d4ed8'; // Darker blue
          opacity = 1.0;
        } else if (isNeighbor && activeNodeId) {
          // Neighbor of active node
          color = 'rgba(37,99,235,0.55)'; // Medium blue
          opacity = 0.9;
        } else if (isHighlighted) {
          // Highlighted but not focused
          color = 'rgba(37,99,235,0.35)'; // Lighter blue
          opacity = 0.7;
        } else {
          // Default node
          color = 'rgba(120,120,120,0.20)'; // Very faint gray
          opacity = 0.5;
        }

        return {
          ...node,
          color,
          opacity,
        };
      });
    }, [nodes, highlightNodeIds, activeNodeId, neighborIds]);

    // Update node materials when colors/opacities change
    useEffect(() => {
      if (graphRef.current) {
        const scene = graphRef.current.scene();
        if (scene) {
          scene.traverse((object: any) => {
            if (object.isMesh && object.__nodeId) {
              const nodeId = object.__nodeId;
              const nodeDataItem = nodeData.find(n => n.id === nodeId);
              if (nodeDataItem && object.material) {
                object.material.color.set(nodeDataItem.color || '#4b5563');
                object.material.emissive.set(nodeDataItem.color || '#4b5563');
                object.material.opacity = nodeDataItem.opacity !== undefined ? nodeDataItem.opacity : 0.9;
                object.material.needsUpdate = true;
              }
            }
          });
        }
      }
    }, [nodeData]);

    // Compute visible link keys (only links connected to activeNodeId)
    const visibleLinkKeys = useMemo(() => {
      if (!activeNodeId) return new Set<string>();
      
      const keys = new Set<string>();
      for (const l of links) {
        const s = getNodeId((l as any).source);
        const t = getNodeId((l as any).target);
        if (s === activeNodeId || t === activeNodeId) {
          keys.add(`${s}__${t}`);
          keys.add(`${t}__${s}`); // allow either orientation
        }
      }
      
      console.info(`[Map] visible links count: ${keys.size / 2}`); // Divide by 2 since we store both orientations
      return keys;
    }, [activeNodeId, links, getNodeId]);

    // Compute link colors and opacities (hidden by default, visible only when activeNodeId is set)
    const linkData = useMemo(() => {
      return links.map((link, index) => {
        const sourceId = getNodeId((link as any).source);
        const targetId = getNodeId((link as any).target);
        const linkKey = `${sourceId}__${targetId}`;
        const isVisible = visibleLinkKeys.has(linkKey);
        
        return {
          ...link,
          color: isVisible ? '#2563eb' : 'rgba(0,0,0,0)', // Hidden if not visible
          opacity: isVisible ? 0.9 : 0, // Fully transparent if not visible
          width: isVisible ? 1.5 : 0, // No width if not visible
          curvature: 0.15 + (index % 3) * 0.05, // Slight curvature variation
          curveRotation: (index % 2) * Math.PI, // Alternate curve direction
        };
      });
    }, [links, visibleLinkKeys, getNodeId]);

    const handleNodeClick = useCallback(
      (node: any) => {
        const nodeId = String(node.id);
        
        // Only allow clicking highlighted nodes
        if (!highlightNodeIds.has(nodeId)) {
          console.info(`[Map] clicked non-highlighted node: ${nodeId} (ignored)`);
          return;
        }
        
        // Set as active node (this will be handled by parent component)
        const graphNode = nodes.find((n) => n.id === node.id);
        if (graphNode) {
          onNodeClick?.(graphNode);
          console.info(`[Map] active highlighted node set: ${nodeId}`);
          
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
      [nodes, highlightNodeIds, onNodeClick]
    );

    const handleNodeHover = useCallback((node: any) => {
      // Tooltip is handled via nodeLabel prop
    }, []);

    // Freeze graph by setting fixed positions for all nodes with spacing scaling
    const freezeGraph = useCallback(() => {
      if (!graphRef.current) return;
      
      try {
        // Access graph data
        const graphData = typeof graphRef.current.graphData === 'function'
          ? graphRef.current.graphData()
          : (graphRef.current as any)?.graphData;
        
        if (!graphData || !graphData.nodes) return;
        
        const nodesToFreeze = graphData.nodes.filter((n: any) => 
          n.x !== undefined && n.y !== undefined && n.z !== undefined &&
          isFinite(n.x) && isFinite(n.y) && isFinite(n.z)
        );
        
        if (nodesToFreeze.length === 0) return;
        
        // Calculate center of mass
        let cx = 0, cy = 0, cz = 0;
        nodesToFreeze.forEach((node: any) => {
          cx += node.x;
          cy += node.y;
          cz += node.z;
        });
        cx /= nodesToFreeze.length;
        cy /= nodesToFreeze.length;
        cz /= nodesToFreeze.length;
        
        // Apply spacing scale: scale each node away from center
        const SPACING_SCALE = spacingScale;
        let frozenCount = 0;
        
        // First, clear all fixed positions to allow scaling
        nodesToFreeze.forEach((node: any) => {
          node.fx = undefined;
          node.fy = undefined;
          node.fz = undefined;
        });
        
        // Then scale positions away from center
        nodesToFreeze.forEach((node: any) => {
          // Scale position away from center (multiply the distance from center)
          const dx = node.x - cx;
          const dy = node.y - cy;
          const dz = node.z - cz;
          
          node.x = cx + dx * SPACING_SCALE;
          node.y = cy + dy * SPACING_SCALE;
          node.z = cz + dz * SPACING_SCALE;
          
          // Freeze at scaled position
          node.fx = node.x;
          node.fy = node.y;
          node.fz = node.z;
          frozenCount++;
        });
        
        console.log(`✅ Frozen ${frozenCount} nodes - graph is now static`);
        console.info(`[Map] post-freeze scale applied: scale=${SPACING_SCALE}, nodes=${frozenCount}, center=(${cx.toFixed(1)}, ${cy.toFixed(1)}, ${cz.toFixed(1)})`);
        console.info(`[Map] spacing tuned: scale=5.0 charge=-500 linkDist=250 linkStrength=0.1 cooldown=250`);
        
        // Remove all forces to prevent them from pulling nodes back together
        graphRef.current.d3Force('center', null);
        graphRef.current.d3Force('link', null);
        graphRef.current.d3Force('charge', null);
        
        // Stop the animation/simulation
        const fg = graphRef.current as any;
        if (typeof fg.stopAnimation === 'function') {
          fg.stopAnimation();
          console.log('🛑 Stopped animation');
        }
        if (typeof fg.pauseAnimation === 'function') {
          fg.pauseAnimation();
          console.log('⏸️ Paused animation');
        }
        
        // Update graph data with frozen positions
        if (typeof graphRef.current.graphData === 'function') {
          graphRef.current.graphData(graphData);
        }
      } catch (error) {
        console.error('❌ Error freezing graph:', error);
      }
    }, [spacingScale]);

    // Apply white background to the graph
    const applyWhiteBackground = useCallback((fg: ForceGraphMethods) => {
      try {
        // Solid white background (Three scene + renderer)
        const scene = fg.scene();
        if (!scene) return;
        
        scene.background = new THREE.Color(0xffffff);

        const renderer = fg.renderer();
        if (!renderer) return;
        
        renderer.setClearColor(0xffffff, 1);
        
        // Don't remove existing lights - just add/adjust them
        // Removing lights can break the scene setup
        const existingLights = scene.children.filter((child: any) => child.isLight);
        
        // Only add lights if we don't have enough
        if (existingLights.length === 0) {
          const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
          scene.add(ambientLight);
          
          const directionalLight = new THREE.DirectionalLight(0xffffff, 0.7);
          directionalLight.position.set(50, 50, 50);
          scene.add(directionalLight);
          
          const pointLight = new THREE.PointLight(0xffffff, 0.5);
          pointLight.position.set(0, 0, 100);
          scene.add(pointLight);
        } else {
          // Adjust existing lights intensity for white background
          existingLights.forEach((light: any) => {
            if (light.isAmbientLight) {
              light.intensity = 0.8;
            } else if (light.isDirectionalLight || light.isPointLight) {
              light.intensity = Math.max(light.intensity, 0.6);
            }
          });
        }
      } catch (error) {
        console.error('Error setting background:', error);
      }
    }, []);

    // Callback ref runs when the instance becomes available (reliable vs useEffect timing)
    const setFgRef = useCallback(
      (fg: ForceGraphMethods | null) => {
        graphRef.current = fg;
        if (!fg) return;
        console.log('FG ref set:', !!fg);
        applyWhiteBackground(fg);
      },
      [applyWhiteBackground]
    );

    // Center camera on graph - use zoomToFit which handles everything
    const centerCameraOnGraph = useCallback(() => {
      if (!graphRef.current) return;

      try {
        // Access graph data - graphData might be a method or property
        const graphData = typeof graphRef.current.graphData === 'function'
          ? graphRef.current.graphData()
          : (graphRef.current as any)?.graphData;
        
        if (!graphData) return;
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
          if (typeof graphRef.current.graphData === 'function') {
            graphRef.current.graphData(graphData);
          }
          
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
      console.log('🛑 Engine stopped');
      
      // Re-apply background when engine stops (some internals finalize after layout settles)
      if (graphRef.current) {
        applyWhiteBackground(graphRef.current);
      }
      
      // Wait a bit then center - need nodes to have settled positions
      setTimeout(() => {
        if (graphRef.current) {
          // Access graph data - graphData might be a method or property
          const graphData = typeof graphRef.current.graphData === 'function'
            ? graphRef.current.graphData()
            : (graphRef.current as any)?.graphData;
          
          if (!graphData) return;
          
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
            // graphData is a method that accepts data to update
            if (graphRef.current && typeof (graphRef.current as any).graphData === 'function') {
              (graphRef.current as any).graphData(graphData);
            }
            
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
        
        // Freeze the graph if not already frozen
        if (!isFrozen) {
          freezeGraph();
          setIsFrozen(true);
        }
        
        // Try setting background again after centering
        if (graphRef.current) {
          applyWhiteBackground(graphRef.current);
        }
      }, 500);
    }, [applyWhiteBackground, freezeGraph, isFrozen]);

    // Configure spacing forces (charge repulsion + link distance) after graph is ready
    useEffect(() => {
      if (graphRef.current && nodes.length > 0) {
        const fg = graphRef.current as any;
        
        // Configure charge force for MUCH stronger repulsion (more spacing)
        const charge = graphRef.current.d3Force('charge');
        if (charge) {
          charge.strength(-500); // MUCH stronger repulsion - negative = push apart
          if (charge.distanceMax) {
            charge.distanceMax(1500); // Much longer range repulsion
          }
        }
        
        // Configure link force for MUCH longer link distances
        const link = graphRef.current.d3Force('link');
        if (link) {
          link.distance(250); // MUCH longer spacing along edges
          link.strength(0.1); // Weaker link force so it doesn't pull nodes together
        }
        
        console.info(`[Map] spacing tuned: scale=5.0 charge=-500 linkDist=250 linkStrength=0.1 cooldown=250`);
      }
    }, [nodes.length]);

    // Add centering force to keep nodes at origin
    useEffect(() => {
      if (graphRef.current && nodes.length > 0) {
        // Add a weak centering force that pulls nodes toward origin
        graphRef.current.d3Force('center', (alpha: number) => {
          try {
            // The d3Force callback receives the simulation as 'this'
            // Nodes are available through the simulation's nodes array
            // We access them via the graph's internal state
            const fg = graphRef.current as any;
            let graphNodes: any[] = [];
            
            // Try multiple ways to access nodes
            if (fg._graphData?.nodes) {
              graphNodes = fg._graphData.nodes;
            } else if (fg._nodes) {
              graphNodes = fg._nodes;
            } else {
              // If we can't access nodes, skip this force
              return;
            }
            
            graphNodes.forEach((node: any) => {
              if (node && node.x !== undefined && node.y !== undefined && node.z !== undefined) {
                // Weak force toward origin
                const strength = 0.05 * alpha;
                node.vx = (node.vx || 0) - node.x * strength;
                node.vy = (node.vy || 0) - node.y * strength;
                node.vz = (node.vz || 0) - node.z * strength;
              }
            });
          } catch (error) {
            // Silently fail if nodes are not accessible
          }
        });
      }
    }, [nodes.length]);

    // Reset frozen state when data changes
    useEffect(() => {
      // Create a hash of the data to detect changes
      const dataHash = `${nodes.length}-${links.length}-${Array.from(nodes.map(n => n.id)).sort().join(',')}`;
      
      if (dataHash !== previousDataHash.current) {
        console.log('📊 Graph data changed - resetting freeze state');
        setIsFrozen(false);
        previousDataHash.current = dataHash;
        hasCenteredRef.current = false;
        hasLoggedEngineStart.current = false; // Reset engine start log for new graph
      }
    }, [nodes, links]);

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
      <div className="absolute inset-0 w-full h-full force-graph-container bg-white">
        <ForceGraph3D
          ref={setFgRef}
          graphData={{ nodes: nodeData, links: linkData }}
          nodeLabel={(node: any) => {
            const graphNode = nodes.find((n) => n.id === node.id);
            if (graphNode) {
              return `${graphNode.name}\n${graphNode.file}:${graphNode.line}`;
            }
            return '';
          }}
          nodeThreeObject={makeNodeObject}
          nodeThreeObjectExtend={true}
          nodeOpacity={(node: any) => {
            // Highlighted nodes are fully opaque, others use node opacity or default
            if (highlightNodeIds.has(node.id)) return 1.0;
            return node.opacity !== undefined ? node.opacity : 0.9;
          }}
          linkColor={(link: any) => {
            // Use pre-computed link color from linkData (handles visibility based on activeNodeId)
            return link.color || 'rgba(0,0,0,0)';
          }}
          linkOpacity={(link: any) => {
            // Use pre-computed link opacity from linkData
            return link.opacity !== undefined ? link.opacity : 0;
          }}
          linkWidth={(link: any) => {
            // Use pre-computed link width from linkData
            return link.width !== undefined ? link.width : 0;
          }}
          linkCurvature={(link: any) => link.curvature !== undefined ? link.curvature : 0.15}
          linkCurveRotation={(link: any) => link.curveRotation !== undefined ? link.curveRotation : 0}
          linkDirectionalArrowLength={2}
          linkDirectionalArrowRelPos={1}
          linkDirectionalArrowOpacity={0.4}
          onNodeClick={handleNodeClick}
          onNodeHover={handleNodeHover}
          enableNodeDrag={false}
          cooldownTicks={250}
          cooldownTime={0}
          onEngineStop={handleEngineStop}
          onEngineTick={() => {
            // Log when engine starts (first tick) - use a ref to prevent multiple logs
            if (!hasLoggedEngineStart.current) {
              console.log('▶️ Engine started - computing initial layout');
              hasLoggedEngineStart.current = true;
            }
          }}
          onRender={() => {
            // Ensure background stays white on every render
            if (graphRef.current) {
              try {
                const scene = graphRef.current.scene();
                const renderer = graphRef.current.renderer();
                if (scene.background) {
                  const bgColor = scene.background as THREE.Color;
                  if (bgColor.getHex() !== 0xffffff) {
                    scene.background = new THREE.Color(0xffffff);
                  }
                }
                renderer.setClearColor(0xffffff, 1);
              } catch (e) {
                // Silently fail
              }
            }
          }}
        />
      </div>
    );
  }
);

CallGraph3D.displayName = 'CallGraph3D';
