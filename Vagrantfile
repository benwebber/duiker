Vagrant.configure("2") do |config|
  config.vm.box = "debian/jessie64"
  config.vm.provision "shell",
    inline: <<EOF
apt install curl jq
curl https://sh.rustup.rs -sSf | sh -s -- -y
cd /vagrant
make dist
EOF
  config.vm.synced_folder ".", "/vagrant", type: "virtualbox"
end
