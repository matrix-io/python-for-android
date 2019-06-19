from os.path import join, isdir, isfile
import sh
from pythonforandroid.recipe import NDKRecipe, CythonRecipe, Recipe
from pythonforandroid.toolchain import current_directory, shprint
from pythonforandroid.logger import info
from multiprocessing import cpu_count
import glob


class GRPCRecipe(CythonRecipe):
    name = "grpc"
    version = "v1.20.1"
    # url = 'https://github.com/grpc/grpc/archive/{version}.zip'
    url = None
    port_git = "https://github.com/grpc/grpc.git"
    depends = ["setuptools"]
    site_packages_name = "grpcio"
    cython_args = ["src/python/grpcio/grpc/_cython"]
    # patches = ["fix_cares.patch"]

    def get_recipe_env(self, arch):
        env = super(GRPCRecipe, self).get_recipe_env(arch)
        build_dir = self.get_build_dir(arch.arch)
        third_party_dir = join(build_dir, "third_party")
        boringssl_dir = join(third_party_dir, "boringssl")
        env["CC"] = "arm-linux-androideabi-gcc "
        # -fno-rtti avoids ImportError: dlopen failed: cannot locate symbol "_ZTVN10__cxxabiv117__class_type_infoE" referenced by "/data/data/com.admobilize.admp/files/app/_python_bundle/site-packages/grpc/_cython/cygrpc.so"
        # This overwrites the CFLAGS used by grpc
        env[
            "GRPC_PYTHON_CFLAGS"
        ] = " -I{} -I/opt/android/android-ndk/sources/cxx-stl/gnu-libstdc++/4.9/include -I/opt/android/android-ndk/sources/cxx-stl/gnu-libstdc++/4.9/libs/armeabi-v7a/include -std=c++11 -std=c99 -fvisibility=hidden -fno-wrapv -fno-exceptions -fpermissive -fno-rtti -w ".format(
            join(boringssl_dir, "include")
        )
        # -llog avoids ImportError: dlopen failed: cannot locate symbol "__android_log_print" referenced by "/data/data/com.admobilize.admp/files/app/_python_bundle/site-packages/grpc/_cython/cygrpc.so"
        # This overwrites the LDFLAGS used by grpc
        env["GRPC_PYTHON_LDFLAGS"] = " -Wl,-wrap,memcpy -static-libgcc -llog -ldl -lm"
        return env

    def prebuild_arch(self, arch):
        build_dir = self.get_build_dir(arch.arch)
        source_dir = join(build_dir, "grpc")
        if not isfile(join(build_dir, "setup.py")) and not isfile(
            join(source_dir, "setup.py")
        ):
            info("clone GRPC sources from {}".format(self.port_git))
            shprint(
                sh.git,
                "clone",
                "--branch",
                self.version,
                "--single-branch",
                "--recursive",
                self.port_git,
                source_dir,
                _tail=20,
                _critical=True,
            )

        if isfile(join(source_dir, "setup.py")):
            shprint(sh.mv, *glob.glob(join(source_dir, "*")), build_dir)
            shprint(sh.rm, "-rf", source_dir)
            # TODO Fix this hardcoded path
            self.apply_patch(
                "/home/user/admp/p4a-recipes/grpc/fix_cares.patch", arch.arch
            )

    def build_arch(self, arch):
        Recipe.build_arch(self, arch)

        self.build_cython_components(arch)
        self.install_python_package(arch)  # this is the same as in a PythonRecipe

    def build_cython_components(self, arch):
        env = self.get_recipe_env(arch)
        build_dir = self.get_build_dir(arch.arch)
        with current_directory(build_dir):
            hostpython = sh.Command(self.ctx.hostpython)

            # We manually run cython from the user's system
            # note the --cplus flag, used to build cygrpc.cpp
            shprint(
                sh.find,
                join(build_dir, self.cython_args[0]),
                "-iname",
                "*.pyx",
                "-exec",
                self.ctx.cython,
                "--cplus",
                "{}",
                ";",
                _env=env,
            )

            # Now that cython has been run, the build works
            try:
                shprint(hostpython, "setup.py", "build_ext", "-v", _env=env)
            except sh.ErrorReturnCode as e:
                for line in str(e.stdout).split("\\n"):
                    print(line)
                raise

            # stripping debug symbols lowers the file size a lot
            build_lib = glob.glob("./python_build/lib*")
            info("{}".format(build_lib))
            shprint(
                sh.find,
                "./python_build/",
                "-name",
                "*.o",
                "-exec",
                env["STRIP"],
                "{}",
                ";",
                _env=env,
            )


recipe = GRPCRecipe()
