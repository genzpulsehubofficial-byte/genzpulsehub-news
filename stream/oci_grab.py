"""GitHub Actions: keep trying to create the Always Free ARM server until Oracle has capacity, then stop.
Secret OCI_CONFIG = base64 JSON made by stream/oci_github_setup.sh in Cloud Shell."""
import base64, json, os, sys, tempfile, urllib.request
import oci

cfg = json.loads(base64.b64decode(os.environ["OCI_CONFIG"]))
kf = tempfile.NamedTemporaryFile("w", delete=False, suffix=".pem"); kf.write(cfg["key"]); kf.close()
conf = {"user": cfg["user"], "tenancy": cfg["tenancy"], "fingerprint": cfg["fingerprint"],
        "region": cfg["region"], "key_file": kf.name}
C = cfg["tenancy"]; NAME = "gph-stream"
comp, net, ident = oci.core.ComputeClient(conf), oci.core.VirtualNetworkClient(conf), oci.identity.IdentityClient(conf)


def discord(msg):
    h = os.environ.get("DISCORD_WEBHOOK_URL")
    if h:
        urllib.request.urlopen(urllib.request.Request(h, json.dumps({"content": "@everyone " + msg}).encode(),
                               {"Content-Type": "application/json", "User-Agent": "gph"}), timeout=15)


live = [i for i in comp.list_instances(C, display_name=NAME).data if i.lifecycle_state in ("RUNNING", "PROVISIONING", "STARTING")]
if live:
    vn = comp.list_vnic_attachments(C, instance_id=live[0].id).data
    ip = net.get_vnic(vn[0].vnic_id).data.public_ip if vn else "?"
    print("server exists:", live[0].lifecycle_state, ip); open("server_ip.txt", "w").write(ip or ""); sys.exit(0)

vcn = next((v for v in net.list_vcns(C).data if v.display_name == "gph-vcn"), None)
if not vcn:
    sys.exit("network gph-vcn missing: run stream/oci_create.sh once in Cloud Shell")
sub = net.list_subnets(C, vcn_id=vcn.id).data[0]
img = comp.list_images(C, operating_system="Canonical Ubuntu", operating_system_version="22.04",
                       shape="VM.Standard.A1.Flex", sort_by="TIMECREATED", sort_order="DESC").data[0]
ud = base64.b64encode(open(os.path.join(os.path.dirname(__file__), "cloud-init.sh"), "rb").read()).decode()
for ocpu, mem in ((4, 24), (2, 12)):
    for ad in ident.list_availability_domains(C).data:
        try:
            inst = comp.launch_instance(oci.core.models.LaunchInstanceDetails(
                compartment_id=C, availability_domain=ad.name, display_name=NAME, shape="VM.Standard.A1.Flex",
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=ocpu, memory_in_gbs=mem),
                source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=img.id, boot_volume_size_in_gbs=100),
                create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=sub.id, assign_public_ip=True),
                metadata={"ssh_authorized_keys": cfg["ssh_pub"], "user_data": ud})).data
            print("CREATED", inst.id, ocpu, "OCPU")
            discord(f"✅ Oracle free server created ({ocpu} CPU / {mem} GB). It installs itself in ~10 min. Next: add stream keys.")
            sys.exit(0)
        except oci.exceptions.ServiceError as e:
            print(ocpu, ad.name, e.status, e.code, str(e.message)[:120])
print("no capacity yet; will retry")
