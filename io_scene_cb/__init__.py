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
from .common_functions import get_shader_node, SHADER_RESOURCES, ObjectType
from .scene_rmesh import update_object

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

if (4, 1, 0) <= bpy.app.version:
    from bpy.types import FileHandler

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

class CBObjectPropertiesGroup(PropertyGroup):
    object_type: EnumProperty(
        name="Type",
        description="Set the classification for the CB object",
        items = ( ('0', "Exclude", "Object is excluded from export"),
                    ('1', "Mesh", "Object is valid for CB/CB-S/UER/UER2"),
                    ('2', "Render", "Object is valid for CB-S"),
                    ('3', "Collision", "Object is valid for CB/CB-S/UER/UER2"),
                    ('4', "Trigger Box", "Object is valid for CB/CB-S"),
                    ('5', "Entity Screen", "Object is valid for CB/CB-S/UER/UER2"),
                    ('6', "Entity Save Screen", "Object is valid for CB/CB-S/UER/UER2"),
                    ('7', "Entity Waypoint", "Object is valid for CB/CB-S/UER/UER2"),
                    ('8', "Entity Light", "Object is valid for CB/CB-S/UER/UER2"),
                    ('9', "Entity Light Fix", "Object is valid for UER/UER2"),
                    ('10', "Entity Spotlight", "Object is valid for CB/CB-S/UER/UER2"),
                    ('11', "Entity Sound Emitter", "Object is valid for CB/CB-S/UER/UER2"),
                    ('12', "Entity Player Start", "Object is valid for CB"),
                    ('13', "Entity Model", "Object is valid for CB/CB-S/UER/UER2"),
                    ('14', "Entity Mesh", "Object is valid for CB/CB-S/UER/UER2"),
                    ('15', "Entity Item", "Object is valid for CB-S"),
                    ('16', "Entity Door", "Object is valid for CB-S"),
                    ('17', "Node Brush", "Object is valid for CB/CB-S/UER/UER2"),
                    ('18', "Node Terrain Sector", "Object is valid for CB/CB-S/UER/UER2"),
                    ('19', "Node Terrain", "Object is valid for CB/CB-S/UER/UER2"),
                    ('20', "Node Mesh", "Object is valid for CB/CB-S/UER/UER2"),
                    ('21', "Node Field Hit", "Object is valid for CB/CB-S/UER/UER2"),
                    ('22', "Node Light", "Object is valid for CB/CB-S/UER/UER2"),
                    ('23', "Node Spotlight", "Object is valid for CB/CB-S/UER/UER2"),
                    ('24', "Node Sunlight", "Object is valid for CB/CB-S/UER/UER2"),
                    ('25', "Node Sound Emitter", "Object is valid for CB/CB-S/UER/UER2"),
                    ('26', "Node Waypoint", "Object is valid for CB/CB-S/UER/UER2"),
                    ('27', "Node Object", "Object is valid for CB/CB-S/UER/UER2")
                )
        )

    model_path: StringProperty(
            name = "Model",
            description="Model to use for this entity",
            default="",
            maxlen=1024,
            subtype='FILE_PATH'
    )

    texture_path: StringProperty(
            name = "Texture",
            description="Texture to use for this entity",
            default="",
            maxlen=1024,
            subtype='FILE_PATH'
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

    item_name: StringProperty(
            name = "Item Name",
            description="The name used for the item when interacted with",
            default="",
    )

    use_custom_rotation: BoolProperty(
        name ="Use Custom Rotation",
        description = "If set to No, the item's rotation will be randomized",
        default = False,
        )

    state_1: FloatProperty(
        name = "State 1",
        description = "Multi-purpose state variable. Exclusively used (for the purposes of a room editor) to represent the remaining power in battery-powered items. 0-1000 for the Night Vision Goggles, 0-100 for all others"
        )
    
    state_2: FloatProperty(
        name = "State 2",
        description = "Second multi-purpose state variable"
        )
    
    spawn_chance: FloatProperty(
        name = "Spawn Chance",
        description = "The chance for this item to spawn. Between 0 and 1 where 1 means a guaranteed spawn and 0.25 means a 25% chance for the item to spawn"
        )

    door_type: EnumProperty(
        name="Door Type",
        description="What type of door is this entity",
        items = ( ('0', "Normal", "The standard doors you'll find in light and entrance"),
                    ('1', "Big", "The larger doors you'll find in containment chambers and gates"),
                    ('2', "Heavy", "The doors you'll find in heavy containment"),
                    ('3', "Elevator", "The doors used for elevators")
                )
        )

    key_card_level: IntProperty(
        name = "Key Card Level",
        description = "The level of keycard required to open this door or 0 for no key card. -1 corresponds to the white severed hand, -2 to the black severed hand. Mutually exclusive with Keypad Code"
        )

    keypad_code: StringProperty(
            name = "Keypad Code",
            description="A numeric four digit code (longer or non-numeric codes render the door unopenable) or an empty string for no code. Mutually exclusive with Key Card Level",
            default="",
    )

    start_open: BoolProperty(
        name ="Start Open",
        description = "Whether the door should spawn open",
        default = False,
        )
    
    locked: BoolProperty(
        name ="Locked",
        description = "Whether the door should be openable by the player",
        default = False,
        )

    delete_half: BoolProperty(
        name ="Delete Half",
        description = "Whether only half of the door should spawn. Useful when there is no space on one side of the door for it to retract into",
        default = False,
        )

    allow_scp_079_remote_control: BoolProperty(
        name ="Allow SCP-079 Remote Control",
        description = "Allow SCP-079 to remotely close the door in front of the player if the remote door control system is enabled",
        default = False,
        )

    button_a_ob: PointerProperty(
        name="Button A Object",
        description="The object being used to represent button A",
        type=bpy.types.Object
    )

    button_b_ob: PointerProperty(
        name="Button B Object",
        description="The object being used to represent button B",
        type=bpy.types.Object
    )

    linear_falloff: FloatProperty(
        name = "Linear Falloff",
        description = "???"
        )

class B3DImagePropertiesGroup(PropertyGroup):
    color: BoolProperty(
        name ="Color",
        description = "???",
        default = True,
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
        default = '2',
        items = ( ('0', "Do Not Blend", "Do Not Blend"),
                    ('1', "No Blend Or Alpha", "No Blend Or Alpha"),
                    ('2', "Multiply", "Multiply"),
                    ('3', "Add", "Add"),
                    ('4', "Dot3", "Dot3"),
                    ('5', "Multiply2", "Multiply2")
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
        props = img.cb

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
    row.operator("cbob.update_ob")
    row = col.row()
    row.label(text='Model Path:')
    row.prop(active_property, "model_path", text='')

def render_entity_mesh(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.operator("cbob.update_ob")
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

def render_entity_item(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.operator("cbob.update_ob")
    row = col.row()
    row.label(text='Item Name:')
    row.prop(active_property, "item_name", text='')
    row = col.row()
    row.label(text='Use Custom Rotation:')
    row.prop(active_property, "use_custom_rotation", text='')
    row = col.row()
    row.label(text='State 1:')
    row.prop(active_property, "state_1", text='')
    row = col.row()
    row.label(text='State 2:')
    row.prop(active_property, "state_2", text='')
    row = col.row()
    row.label(text='Spawn Chance:')
    row.prop(active_property, "spawn_chance", text='')

def render_entity_door(context, layout, active_property):
    box = layout.split()
    col = box.column(align=True)
    row = col.row()
    row.operator("cbob.update_ob")
    row = col.row()
    row.label(text='Door Type:')
    row.prop(active_property, "door_type", text='')
    row = col.row()
    row.label(text='Key Card Level:')
    row.prop(active_property, "key_card_level", text='')
    row = col.row()
    row.label(text='Keypad Code:')
    row.prop(active_property, "keypad_code", text='')
    row = col.row()
    row.label(text='Start Open:')
    row.prop(active_property, "start_open", text='')
    row = col.row()
    row.label(text='Locked:')
    row.prop(active_property, "locked", text='')
    if not active_property.door_type == '3':
        row = col.row()
        row.label(text='Delete Half:')
        row.prop(active_property, "delete_half", text='')

    row = col.row()
    row.label(text='Allow SCP-079 Remote Control:')
    row.prop(active_property, "allow_scp_079_remote_control", text='')
    row = col.row()
    row.label(text='Button A:')
    row.prop(active_property, "button_a_ob", text='')
    row = col.row()
    row.label(text='Button B:')
    row.prop(active_property, "button_b_ob", text='')

class CBOB_OT_UpdateOb(Operator):
    bl_idname = "cbob.update_ob"
    bl_label = "Update Object"
    bl_description = "When clicked the active object in the scene is update to match the entity settings set"

    def execute(self, context):
        update_object(context, self.report)

        return {'FINISHED'}

class CB_ObjectProps(Panel):
    bl_label = "CB Object Properties"
    bl_idname = "CB_PT_ObjectDetailsPanel"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(self, context):
        valid = False
        ob = context.object

        if hasattr(ob, 'cb'):
            valid = True

        return valid

    def draw(self, context):
        layout = self.layout

        ob = context.object
        ob_cb = ob.cb
        col = layout.column(align=True)
        row = col.row()
        row.label(text='Object Type:')
        row.prop(ob_cb, "object_type", text='')
        object_type = ObjectType(int(ob_cb.object_type))
        if object_type == ObjectType.trigger_box:
            render_trigger(context, layout, ob_cb)
        elif object_type == ObjectType.entity_screen:
            render_screen(context, layout, ob_cb)
        elif object_type == ObjectType.entity_save_screen:
            render_save_screen(context, layout, ob_cb)
        elif object_type == ObjectType.entity_light:
            render_entity_light(context, layout, ob_cb)
        elif object_type == ObjectType.entity_light_fix:
            render_entity_light(context, layout, ob_cb)
        elif object_type == ObjectType.entity_spotlight:
            render_entity_light(context, layout, ob_cb)
        elif object_type == ObjectType.entity_sound_emitter:
            render_sound_emitter(context, layout, ob_cb)
        elif object_type == ObjectType.entity_model:
            render_entity_model(context, layout, ob_cb)
        elif object_type == ObjectType.entity_mesh:
            render_entity_mesh(context, layout, ob_cb)
        elif object_type == ObjectType.entity_item:
            render_entity_item(context, layout, ob_cb)
        elif object_type == ObjectType.entity_door:
            render_entity_door(context, layout, ob_cb)

class CBRMAT_OT_CBShader(Operator):
    bl_idname = "node.cb_material"
    bl_label = "CB Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        node_tree = context.space_data.edit_tree

        shader_node = get_shader_node(node_tree, SHADER_RESOURCES, "cb_material")
        shader_node.location = context.space_data.cursor_location

        return {'FINISHED'}

class ExportRMESH(Operator, ExportHelper):
    """Write an RMESH file"""
    bl_idname = 'export_scene.ermesh'
    bl_label = 'Export RMESH'
    filename_ext = ''

    file_type: EnumProperty(
        name="File Type:",
        description="What game was the model file made for",
        items=[ ('0', "RMESH", "Export an RMESH intended for the original SCP CB"),
                ('2', "RMESH UER", "Export an RMESH intended for SCP CB UER 1.5.6"),
                ('3', "RMESH UER 2", "Export an RMESH intended for SCP CB UER 2.0"),
                ('4', "RM", "Export an RMESH intended for the Salvage SCP CB fork")
            ]
        )

    filter_glob: StringProperty(
        default="*.rmesh;*.rm",
        options={'HIDDEN'},
        )

    def execute(self, context):
        from . import scene_rmesh

        return scene_rmesh.export_scene(context, Path(self.filepath), self.file_type, self.report)

class ImportRMESH(Operator, ImportHelper):
    """Import an RMESH file"""
    bl_idname = "import_scene.irmesh"
    bl_label = "Import RMESH"
    filename_ext = ''

    file_type: EnumProperty(
        name="File Type:",
        description="What game was the model file made for",
        items=[ ('0', "Auto", "Attempt to automatically get the correct file type. May cause problems if the app is trying to guess between UER and release files."),
                ('1', "RMESH", "Import an RMESH intended for the original SCP CB"),
                ('2', "RMESH Trigger Box", "Import an RMESH intended for the original SCP CB"),
                ('3', "RMESH UER", "Import an RMESH intended for SCP CB UER 1.5.6"),
                ('4', "RMESH UER 2", "Import an RMESH intended for SCP CB UER 2.0"),
                ('5', "RM", "Import an RMESH intended for the Salvage SCP CB fork"),
            ]
        )

    fullbright_materials: BoolProperty(
        name ="Enable Fullbright Materials",
        description = "Materials will include the lightmap images but not use them in the display",
        default = False,
        )

    filter_glob: StringProperty(
        default="*.rmesh;*.rm",
        options={'HIDDEN'},
        )

    filepath: StringProperty(
        subtype='FILE_PATH',
        options={'SKIP_SAVE'}
        )

    def execute(self, context):
        from . import scene_rmesh

        return scene_rmesh.import_scene(context, Path(self.filepath), self.file_type, self.fullbright_materials, self.report)

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

    filter_glob: StringProperty(
        default="*.x",
        options={'HIDDEN'},
        )

    def execute(self, context):
        from . import scene_x

        return scene_x.export_scene(context, Path(self.filepath), self.report)

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

        return scene_b3d.export_scene(context, Path(self.filepath), self.report)

class ImportB3D(Operator, ImportHelper):
    """Import a B3D file"""
    bl_idname = "import_scene.ib3d"
    bl_label = "Import B3D"
    filename_ext = '.b3d'

    fullbright_materials: BoolProperty(
        name ="Enable Fullbright Materials",
        description = "Materials will include the lightmap images but not use them in the display",
        default = False,
        )

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

        return scene_b3d.import_scene(context, Path(self.filepath), self.fullbright_materials, self.report)

    if (4, 1, 0) <= bpy.app.version:
        def invoke(self, context, event):
            if self.filepath:
                return self.execute(context)
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}

class ImportSMF(Operator, ImportHelper):
    """Import an SMF file"""
    bl_idname = "import_scene.ismf"
    bl_label = "Import SMF"
    filename_ext = '.smf'

    filter_glob: StringProperty(
        default="*.smf",
        options={'HIDDEN'},
        )

    filepath: StringProperty(
        subtype='FILE_PATH',
        options={'SKIP_SAVE'}
        )

    def execute(self, context):
        from . import scene_smf

        return scene_smf.import_scene(context, Path(self.filepath), self.report)

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

    class ImportSMF_FileHandler(FileHandler):
        bl_idname = "SMF_FH_import"
        bl_label = "File handler for SMF import"
        bl_import_operator = "import_scene.ismf"
        bl_file_extensions = "smf"

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
    self.layout.operator(ImportSMF.bl_idname, text='SCP SMF (.smf)')

def menu_func_cb_shaders(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("node.cb_material", text="CB Material")

classesscp = [
    ImportRMESH,
    ExportRMESH,
    ImportX,
    ExportX,
    ImportB3D,
    ExportB3D,
    ImportSMF,
    CBObjectPropertiesGroup,
    CB_ObjectProps,
    B3DImagePropertiesGroup,
    B3DIMAGE_PT_SceneProps,
    CBRMAT_OT_CBShader,
    SCPCBAddonPrefs,
    CBOB_OT_UpdateOb
]

if (4, 1, 0) <= bpy.app.version:
    classesscp.append(ImportRMESH_FileHandler)
    classesscp.append(ImportX_FileHandler)
    classesscp.append(ImportB3D_FileHandler)
    classesscp.append(ImportSMF_FileHandler)

def register():
    for clsscp in classesscp:
        bpy.utils.register_class(clsscp)

    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.NODE_MT_category_shader_shader.append(menu_func_cb_shaders)
    bpy.types.Object.cb = PointerProperty(type=CBObjectPropertiesGroup, name="RMESH Properties", description="Set properties for your rmesh object")
    bpy.types.Image.cb = PointerProperty(type=B3DImagePropertiesGroup)

def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.NODE_MT_category_shader_shader.remove(menu_func_cb_shaders)
    for clsscp in classesscp:
        bpy.utils.unregister_class(clsscp)

    del bpy.types.Object.cb
    del bpy.types.Image.cb

if __name__ == '__main__':
    register()
