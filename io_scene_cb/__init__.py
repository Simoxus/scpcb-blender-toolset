bl_info = {
    "name": "SCP CB Toolset",
    "author": "General_101",
    "version": (117, 343, 65521),
    "blender": (4, 0, 0),
    "location": "File > Import-Export",
    "description": "Import-Export SCP CB and UER game assets Build: BUILD_VERSION_STR",
    "warning": "",
    "support": 'COMMUNITY',
    "category": "Import-Export"}

import bpy

from pathlib import Path

from bpy.types import (
        PropertyGroup,
        Operator,
        Panel
        )
from bpy.props import (
        IntProperty,
        BoolProperty,
        EnumProperty,
        FloatProperty,
        StringProperty,
        PointerProperty,
        CollectionProperty
        )
from bpy_extras.io_utils import (
    ImportHelper,
    ExportHelper
    )

from enum import Flag, Enum, auto
if (4, 1, 0) <= bpy.app.version:
    from bpy.types import FileHandler

class ObjectType(Enum):
    exclude = 0
    mesh = auto()
    collision = auto()
    trigger_box = auto()
    entity_screen = auto()
    entity_save_screen = auto()
    entity_waypoint = auto()
    entity_light = auto()
    entity_light_fix = auto()
    entity_spotlight = auto()
    entity_sound_emitter = auto()
    entity_player_start = auto()
    entity_model = auto()
    entity_mesh = auto()

class SCPCBAddonPrefs(bpy.types.AddonPreferences):
    bl_idname = __name__
    game_path: StringProperty(
        name="Game Path",
        description="Path to the game directory",
        subtype="DIR_PATH"
    )

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="Addon Options:")
        col = box.column(align=True)
        row = col.row()
        row.label(text='Game Path:')
        row.prop(self, "game_path", text='')

class RMESHObjectPropertiesGroup(PropertyGroup):
    object_type: EnumProperty(
        name="Type",
        description="Set the classification for the RMESH object",
        items = ( ('0', "Exclude", "Object is excluded from export"),
                    ('1', "Mesh", "Object is valid for CB/UER/UER2"),
                    ('2', "Collision", "Object is valid for CB/UER/UER2"),
                    ('3', "Trigger Box", "Object is valid for CB"),
                    ('4', "Entity Screen", "Object is valid for CB/UER/UER2"),
                    ('5', "Entity Save Screen", "Object is valid for CB/UER/UER2"),
                    ('6', "Entity Waypoint", "Object is valid for CB/UER/UER2"),
                    ('7', "Entity Light", "Object is valid for CB/UER/UER2"),
                    ('8', "Entity Light Fix", "Object is valid for UER/UER2"),
                    ('9', "Entity Spotlight", "Object is valid for CB/UER/UER2"),
                    ('10', "Entity Sound Emitter", "Object is valid for CB/UER/UER2"),
                    ('11', "Entity Player Start", "Object is valid for CB"),
                    ('12', "Entity Model", "Object is valid for CB/UER/UER2"),
                    ('13', "Entity Mesh", "Object is valid for CB/UER/UER2")
                )
        )

    model_path: StringProperty(
            name = "Model",
            description="Model to use for this entity",
            default="",
            maxlen=1024,
            subtype='DIR_PATH'
    )

    texture_path: StringProperty(
            name = "Texture",
            description="Texture to use for this entity",
            default="",
            maxlen=1024,
            subtype='DIR_PATH'
    )

    trigger_group: StringProperty(
            name = "Trigger Group",
            description="Group for this trigger",
            default="",
    )

    sound_emitter_id: IntProperty(
        name = "Sound Emitter ID",
        description = "???"
        )

    has_collision: BoolProperty(
        name ="Has Collision",
        description = "Is the object collidable",
        default = False,
        )

    fx: IntProperty(
        name = "FX",
        description = "???"
        )

    has_sprite: BoolProperty(
        name ="Has Sprite",
        description = "Has Sprite",
        default = False,
        )

    sprite_scale: FloatProperty(
        name = "Sprite Scale",
        description = "???"
        )

    scattering: FloatProperty(
        name = "Scattering",
        description = "???"
        )

class B3DImagePropertiesGroup(PropertyGroup):
    color: BoolProperty(
        name ="Color",
        description = "???",
        default = False,
        )

    alpha: BoolProperty(
        name ="Alpha",
        description = "???",
        default = False,
        )

    masked: BoolProperty(
        name ="Masked",
        description = "???",
        default = False,
        )

    mipmapped: BoolProperty(
        name ="Mipmapped",
        description = "???",
        default = False,
        )

    clamp_u: BoolProperty(
        name ="Clamp U",
        description = "???",
        default = False,
        )
    
    clamp_v: BoolProperty(
        name ="Clamp V",
        description = "???",
        default = False,
        )

    spherical_environment_map: BoolProperty(
        name ="Spherical Environment Map",
        description = "???",
        default = False,
        )

    cubic_environment_map: BoolProperty(
        name ="Cubic Environment Map",
        description = "???",
        default = False,
        )

    store_texture_in_vram: BoolProperty(
        name ="Store Texture In Vram",
        description = "???",
        default = False,
        )

    force_high_color_textures: BoolProperty(
        name ="Force High Color Textures",
        description = "???",
        default = False,
        )

    blend_type: EnumProperty(
        name="Blend Type",
        description="Set the blend type",
        items = ( ('0', "Do Not Blend", "Do Not Blend"),
                    ('1', "No Blend Or Alpha", "No Blend Or Alpha"),
                    ('2', "Multiply", "Multiply"),
                    ('3', "Add", "Add"),
                    ('4', "Dot3", "Dot3"),
                    ('5', "Multiply2", "Multiply2")
                )
        )

class B3DMaterialPropertiesGroup(PropertyGroup):
    full_bright: BoolProperty(
        name ="Full Bright",
        description = "???",
        default = False,
        )

    use_vertex_colors_instead_of_brush_color: BoolProperty(
        name ="Use Vertex Colors Instead Of Brush Color",
        description = "???",
        default = False,
        )

    flatshaded: BoolProperty(
        name ="Flatshaded",
        description = "???",
        default = False,
        )

    disable_fog: BoolProperty(
        name ="Disable Fog",
        description = "???",
        default = False,
        )

    disable_backface_culling: BoolProperty(
        name ="Disable Backface Culling",
        description = "???",
        default = False,
        )
    
    unk5: BoolProperty(
        name ="Unk 5",
        description = "???",
        default = False,
        )

    blend_type: EnumProperty(
        name="Blend Type",
        description="Set the blend type",
        items = ( ('0', "Alpha", "Alpha"),
                    ('1', "Multiply", "Multiply"),
                    ('2', "Add", "Add")
                )
        )

class B3DIMAGE_PT_SceneProps(Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "B3D"
    bl_label = "B3D Image Properties"

    @classmethod
    def poll(cls, context):
        return context.space_data.image is not None

    def draw(self, context):
        layout = self.layout
        img = context.space_data.image
        props = img.b3d

        layout.prop(props, "color")
        layout.prop(props, "alpha")
        layout.prop(props, "masked")
        layout.prop(props, "mipmapped")
        layout.prop(props, "clamp_u")
        layout.prop(props, "clamp_v")
        layout.prop(props, "spherical_environment_map")
        layout.prop(props, "cubic_environment_map")
        layout.prop(props, "store_texture_in_vram")
        layout.prop(props, "force_high_color_textures")
        layout.prop(props, "blend_type")

class B3DMATERIAL_PT_SceneProps(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_label = "B3D Material Properties"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.material is not None

    def draw(self, context):
        layout = self.layout
        mat = context.material
        props = mat.b3d

        layout.prop(props, "full_bright")
        layout.prop(props, "use_vertex_colors_instead_of_brush_color")
        layout.prop(props, "flatshaded")
        layout.prop(props, "disable_fog")
        layout.prop(props, "disable_backface_culling")
        layout.prop(props, "unk5")
        layout.prop(props, "blend_type")

def render_trigger(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Trigger Group:')
    row.prop(active_property, "trigger_group", text='')

def render_screen(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Texture Path:')
    row.prop(active_property, "texture_path", text='')

def render_save_screen(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Model Path:')
    row.prop(active_property, "model_path", text='')
    row = col.row()
    row.label(text='Texture Path:')
    row.prop(active_property, "texture_path", text='')

def render_entity_light(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Has Sprite:')
    row.prop(active_property, "has_sprite", text='')
    row = col.row()
    row.label(text='Sprite Scale:')
    row.prop(active_property, "sprite_scale", text='')

def render_sound_emitter(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Sound Emitter ID:')
    row.prop(active_property, "sound_emitter_id", text='')

def render_entity_model(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Model Path:')
    row.prop(active_property, "model_path", text='')

def render_entity_mesh(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.label(text='Model Path:')
    row.prop(active_property, "model_path", text='')
    row = col.row()
    row.label(text='Texture Path:')
    row.prop(active_property, "texture_path", text='')
    row = col.row()
    row.label(text='Has Collision:')
    row.prop(active_property, "has_collision", text='')
    row = col.row()
    row.label(text='FX:')
    row.prop(active_property, "fx", text='')

class RMESH_ObjectProps(Panel):
    bl_label = "Rmesh Object Properties"
    bl_idname = "RMESH_PT_ObjectDetailsPanel"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(self, context):
        valid = False
        ob = context.object

        if hasattr(ob, 'rmesh'):
            valid = True

        return valid

    def draw(self, context):
        layout = self.layout

        ob = context.object
        ob_rmesh = ob.rmesh
        col = layout.column(align=True)
        row = col.row()
        row.label(text='Object Type:')
        row.prop(ob_rmesh, "object_type", text='')
        object_type = ObjectType(int(ob_rmesh.object_type))
        if object_type == ObjectType.trigger_box:
            render_trigger(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_screen:
            render_screen(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_save_screen:
            render_save_screen(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_light:
            render_entity_light(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_light_fix:
            render_entity_light(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_spotlight:
            render_entity_light(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_sound_emitter:
            render_sound_emitter(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_model:
            render_entity_model(context, layout, ob_rmesh)
        elif object_type == ObjectType.entity_mesh:
            render_entity_mesh(context, layout, ob_rmesh)

class ExportRMESH(Operator, ExportHelper):
    """Write an RMESH file"""
    bl_idname = 'export_scene.ermesh'
    bl_label = 'Export RMESH'
    filename_ext = '.rmesh'

    file_type: EnumProperty(
        name="File Type:",
        description="What game was the model file made for",
        items=[ ('0', "RMESH", "Import an RMESH intended for the original SCP CB"),
                ('1', "RMESH Trigger Box", "Import an RMESH intended for the original SCP CB"),
                ('2', "RMESH UER", "Import an RMESH intended for SCP CB UER 1.5.6"),
                ('3', "RMESH UER 2", "Import an RMESH intended for SCP CB UER 2.0"),
            ]
        )

    filter_glob: StringProperty(
        default="*.rmesh",
        options={'HIDDEN'},
        )

    def execute(self, context):
        from . import scene_rmesh

        return scene_rmesh.export_scene(context, Path(self.filepath), self.file_type, self.report)

class ImportRMESH(Operator, ImportHelper):
    """Import an RMESH file"""
    bl_idname = "import_scene.irmesh"
    bl_label = "Import RMESH"
    filename_ext = '.rmesh'

    file_type: EnumProperty(
        name="File Type:",
        description="What game was the model file made for",
        items=[ ('0', "Auto", "Attempt to automatically get the correct file type. May cause problems if the app is trying to guess between UER and release files."),
                ('1', "RMESH", "Import an RMESH intended for the original SCP CB"),
                ('2', "RMESH Trigger Box", "Import an RMESH intended for the original SCP CB"),
                ('3', "RMESH UER", "Import an RMESH intended for SCP CB UER 1.5.6"),
                ('4', "RMESH UER 2", "Import an RMESH intended for SCP CB UER 2.0"),
            ]
        )

    filter_glob: StringProperty(
        default="*.rmesh",
        options={'HIDDEN'},
        )

    filepath: StringProperty(
        subtype='FILE_PATH',
        options={'SKIP_SAVE'}
        )

    def execute(self, context):
        from . import scene_rmesh

        return scene_rmesh.import_scene(context, Path(self.filepath), self.file_type, self.report)

    if (4, 1, 0) <= bpy.app.version:
        def invoke(self, context, event):
            if self.filepath:
                return self.execute(context)
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}

class ExportX(Operator, ExportHelper):
    """Write an X file"""
    bl_idname = 'export_scene.ex'
    bl_label = 'Export X'
    filename_ext = '.x'

    file_version: EnumProperty(
        name="File Version:",
        description="What version to use for the X file",
        items=[ ('0', "xof 0302txt 0064", "xof 0302txt 0064"),
                ('1', "xof 0303txt 0032", "xof 0303txt 0032"),
                ('2', "xof 0303bin 0032", "xof 0303bin 0032"),
                ('3', "xof 0303bzip0032", "xof 0303bzip0032"),
            ]
        )

    filter_glob: StringProperty(
        default="*.x",
        options={'HIDDEN'},
        )

    def execute(self, context):
        from . import scene_x

        return scene_x.export_scene(context, Path(self.filepath), self.file_version, self.report)

class ImportX(Operator, ImportHelper):
    """Import an X file"""
    bl_idname = "import_scene.ix"
    bl_label = "Import X"
    filename_ext = '.x'

    filter_glob: StringProperty(
        default="*.x",
        options={'HIDDEN'},
        )

    filepath: StringProperty(
        subtype='FILE_PATH',
        options={'SKIP_SAVE'}
        )

    def execute(self, context):
        from . import scene_x

        return scene_x.import_scene(context, Path(self.filepath), self.report)

    if (4, 1, 0) <= bpy.app.version:
        def invoke(self, context, event):
            if self.filepath:
                return self.execute(context)
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}

class ExportB3D(Operator, ExportHelper):
    """Write an B3D file"""
    bl_idname = 'export_scene.eb3d'
    bl_label = 'Export B3D'
    filename_ext = '.b3d'

    filter_glob: StringProperty(
        default="*.b3d",
        options={'HIDDEN'},
        )

    def execute(self, context):
        from . import scene_b3d

        return scene_b3d.export_scene(context, self.filepath, self.report)

class ImportB3D(Operator, ImportHelper):
    """Import a B3D file"""
    bl_idname = "import_scene.ib3d"
    bl_label = "Import B3D"
    filename_ext = '.b3d'

    filter_glob: StringProperty(
        default="*.b3d",
        options={'HIDDEN'},
        )

    filepath: StringProperty(
        subtype='FILE_PATH',
        options={'SKIP_SAVE'}
        )

    def execute(self, context):
        from . import scene_b3d

        return scene_b3d.import_scene(context, Path(self.filepath), self.report)

    if (4, 1, 0) <= bpy.app.version:
        def invoke(self, context, event):
            if self.filepath:
                return self.execute(context)
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}

if (4, 1, 0) <= bpy.app.version:
    class ImportRMESH_FileHandler(FileHandler):
        bl_idname = "RMESH_FH_import"
        bl_label = "File handler for RMESH import"
        bl_import_operator = "import_scene.ermesh"
        bl_file_extensions = ".rmesh"

        @classmethod
        def poll_drop(cls, context):
            return (context.area and context.area.type == 'VIEW_3D')

    class ImportX_FileHandler(FileHandler):
        bl_idname = "X_FH_import"
        bl_label = "File handler for X import"
        bl_import_operator = "import_scene.ix"
        bl_file_extensions = ".x"

        @classmethod
        def poll_drop(cls, context):
            return (context.area and context.area.type == 'VIEW_3D')

    class ImportB3D_FileHandler(FileHandler):
        bl_idname = "B3D_FH_import"
        bl_label = "File handler for B3D import"
        bl_import_operator = "import_scene.ib3d"
        bl_file_extensions = ".b3d"

        @classmethod
        def poll_drop(cls, context):
            return (context.area and context.area.type == 'VIEW_3D')

def menu_func_export(self, context):
    self.layout.operator(ExportRMESH.bl_idname, text='SCP RMESH (.rmesh)')
    self.layout.operator(ExportX.bl_idname, text='SCP X (.x)')
    self.layout.operator(ExportB3D.bl_idname, text='SCP B3D (.b3d)')

def menu_func_import(self, context):
    self.layout.operator(ImportRMESH.bl_idname, text='SCP RMESH (.rmesh)')
    self.layout.operator(ImportX.bl_idname, text='SCP X (.x)')
    self.layout.operator(ImportB3D.bl_idname, text='SCP B3D (.b3d)')

classesscp = [
    ImportRMESH,
    ExportRMESH,
    ImportX,
    ExportX,
    ImportB3D,
    ExportB3D,
    RMESHObjectPropertiesGroup,
    RMESH_ObjectProps,
    B3DImagePropertiesGroup,
    B3DMaterialPropertiesGroup,
    B3DIMAGE_PT_SceneProps,
    B3DMATERIAL_PT_SceneProps
]

if (4, 1, 0) <= bpy.app.version:
    classesscp.append(ImportRMESH_FileHandler)
    classesscp.append(ImportX_FileHandler)
    classesscp.append(ImportB3D_FileHandler)

def register():
    bpy.utils.register_class(SCPCBAddonPrefs)
    for clsscp in classesscp:
        bpy.utils.register_class(clsscp)

    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.Object.rmesh = PointerProperty(type=RMESHObjectPropertiesGroup, name="RMESH Properties", description="Set properties for your rmesh object")
    bpy.types.Image.b3d = PointerProperty(type=B3DImagePropertiesGroup)
    bpy.types.Material.b3d = PointerProperty(type=B3DMaterialPropertiesGroup)


def unregister():
    del bpy.types.Image.b3d
    del bpy.types.Material.b3d

    bpy.utils.unregister_class(SCPCBAddonPrefs)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    del bpy.types.Object.rmesh
    for clsscp in classesscp:
        bpy.utils.unregister_class(clsscp)

if __name__ == '__main__':
    register()
