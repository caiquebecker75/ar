// Renderiza um .usdz com o SceneKit (motor da Apple, com descarte de verso como no iPhone)
// para conferir o arquivo do Quick Look sem precisar de um aparelho.
//
//   swift tools/render-usdz.swift <display.usdz> <saida.png>
//
// Gera uma faixa com 4 vistas: frente, 3/4, lateral e costas.
import AppKit
import SceneKit

let args = CommandLine.arguments
let scene = try SCNScene(url: URL(fileURLWithPath: args[1]), options: nil)
let (minB, maxB) = scene.rootNode.boundingBox
let height = CGFloat(maxB.y - minB.y)
let target = SCNVector3(0, height * 0.5, 0)

let renderer = SCNRenderer(device: MTLCreateSystemDefaultDevice(), options: nil)
renderer.scene = scene
renderer.autoenablesDefaultLighting = true
scene.background.contents = NSColor(white: 0.93, alpha: 1)

let camNode = SCNNode()
camNode.camera = SCNCamera()
camNode.camera!.fieldOfView = 32
camNode.camera!.zNear = 0.01
scene.rootNode.addChildNode(camNode)
renderer.pointOfView = camNode

let size = CGSize(width: 600, height: 700)
var shots: [NSImage] = []
for angle in [0.0, 35.0, 90.0, 180.0] {
    let r = height * 2.0, a = angle * .pi / 180
    camNode.position = SCNVector3(r * CGFloat(sin(a)), height * 0.75, r * CGFloat(cos(a)))
    camNode.look(at: target)
    shots.append(renderer.snapshot(atTime: 0, with: size, antialiasingMode: .multisampling4X))
}

let strip = NSImage(size: CGSize(width: size.width * CGFloat(shots.count), height: size.height))
strip.lockFocus()
for (i, img) in shots.enumerated() {
    img.draw(in: CGRect(x: CGFloat(i) * size.width, y: 0, width: size.width, height: size.height))
}
strip.unlockFocus()
let rep = NSBitmapImageRep(data: strip.tiffRepresentation!)!
try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: args[2]))
print("ok \(args[2])")
