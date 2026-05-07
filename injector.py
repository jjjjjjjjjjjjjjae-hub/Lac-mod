import UnityPy
import os

def almas_33_system():
    data_file = 'data.unity3d'
    model_path = 'knife_model.glb'
    anim_path = 'knife_anim.fbx'
    
    if not os.path.exists(data_file):
        print("Қате: data.unity3d файлы табылмады!")
        return

    print("--- Almas 33 System: Инъекция басталуда ---")
    env = UnityPy.load(data_file)
    
    with open(model_path, 'rb') as f:
        new_model = f.read()
    
    new_anim = None
    if os.path.exists(anim_path):
        with open(anim_path, 'rb') as f:
            new_anim = f.read()

    for obj in env.objects:
        if obj.path_id == 345:
            obj.set_raw_data(new_model)
            print("[OK] Mesh ID 345: Керамбит орнатылды.")
        elif obj.path_id == 216 and new_anim:
            obj.set_raw_data(new_anim)
            print("[OK] Anim ID 216: Spin анимациясы енгізілді.")

    with open('data_modded.unity3d', 'wb') as f:
        f.write(env.file.save())
    
    print("\n--- НӘТИЖЕ: 'data_modded.unity3d' дайын! ---")

if __name__ == "__main__":
    almas_33_system()
