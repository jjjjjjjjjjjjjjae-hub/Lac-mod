import UnityPy
import os

def inject_mod(target_id, model_path, animation_path):
    # data.unity3d файлын жүктейміз
    env = UnityPy.load('data.unity3d')
    
    # Модельді (Mesh) ауыстыру
    with open(model_path, 'rb') as f:
        new_model_data = f.read()

    # Анимацияны (AnimationClip) ауыстыру
    with open(animation_path, 'rb') as f:
        new_anim_data = f.read()

    for obj in env.objects:
        # Пышақтың моделін ID бойынша табамыз (мысалы 345 немесе 353)
        if obj.path_id == target_id:
            obj.set_raw_data(new_model_data)
            print(f"Модель сәтті ауыстырылды! ID: {target_id}")
        
        # Анимацияны ID бойынша табамыз (бағанағы 216 - WeaponSpin)
        if obj.path_id == 216:
            obj.set_raw_data(new_anim_data)
            print("Анимация (Spin) сәтті ауыстырылды!")

    # Өзгертілген файлды сақтаймыз
    with open('data_modded.unity3d', 'wb') as f:
        f.write(env.file.save())
    print("Дайын! 'data_modded.unity3d' файлы жасалды.")

if __name__ == "__main__":
    # Сынақ ретінде 345 (dingus) ID-ін қолданамыз
    inject_mod(345, 'Зуб Нож.glb', 'Knife Idle.fbx')

