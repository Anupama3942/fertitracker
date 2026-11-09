import datetime
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction

from core.models import Warehouse, ASCCentre, Season, FertilizerProduct
from inventory.models import FertilizerBatch, StockDispatch, DispatchItem, ASCStock, StockMovement, Discrepancy
from farmers.models import Farmer, FarmerEntitlement, QRToken
from distributions.models import FertilizerDistribution, AuditLog, AssistedIssueApproval, SMSOutbox

User = get_user_model()


class Command(BaseCommand):
    help = "Seed realistic demo data for university viva demonstration and ICT Expo 5.0."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Purge existing demo data before seeding new records.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force seeding even if DEMO_MODE is not enabled in settings.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        # DEMO_MODE Safeguard
        if not getattr(settings, 'DEMO_MODE', False) and not options.get('force'):
            raise CommandError(
                "seed_demo_data is restricted to environments where DEMO_MODE=True in .env/settings. "
                "Use --force to override this safeguard."
            )

        reset = options.get('reset', False)

        if reset:
            self.stdout.write(self.style.WARNING("Reset flag detected. Purging existing application data..."))
            SMSOutbox.objects.all().delete()
            QRToken.objects.all().delete()
            FertilizerDistribution.objects.all().delete()
            AssistedIssueApproval.objects.all().delete()
            StockMovement.objects.all().delete()
            Discrepancy.objects.all().delete()
            DispatchItem.objects.all().delete()
            StockDispatch.objects.all().delete()
            ASCStock.objects.all().delete()
            FarmerEntitlement.objects.all().delete()
            Farmer.objects.all().delete()
            FertilizerBatch.objects.all().delete()
            FertilizerProduct.objects.all().delete()
            Season.objects.all().delete()
            ASCCentre.objects.all().delete()
            Warehouse.objects.all().delete()
            # Delete demo users except existing supers not matching demo usernames
            User.objects.filter(username__in=['admin', 'wh_officer', 'asc_officer', 'asc_head', 'auditor', 'farmer1']).delete()
            self.stdout.write(self.style.SUCCESS("Purged old demo data successfully."))

        self.stdout.write("Seeding FertiTracker demo data...")

        # 1. Warehouses (2 Warehouses: Colombo Port Terminal + Northern Regional Hub)
        wh_colombo, _ = Warehouse.objects.get_or_create(
            name="Colombo Port Central Terminal",
            defaults={"location": "Port Access Road, Colombo 13, Western Province"}
        )
        wh_vavuniya, _ = Warehouse.objects.get_or_create(
            name="Northern Regional Distribution Hub",
            defaults={"location": "Industrial Zone, Vavuniya, Northern Province"}
        )
        self.stdout.write("  [OK] 2 Warehouses configured.")

        # 2. Agrarian Service Centres (5 Vavuniya / Northern ASCs)
        ascs_data = [
            ("Vavuniya South ASC", "Vavuniya", "Kandy Road, Vavuniya South"),
            ("Cheddikulam ASC", "Vavuniya", "Mannar Road, Cheddikulam"),
            ("Nedunkeni ASC", "Vavuniya", "Mullaitivu Road, Nedunkeni"),
            ("Omanthai ASC", "Vavuniya", "A9 Highway, Omanthai"),
            ("Puliyankulam ASC", "Vavuniya", "Main Street, Puliyankulam"),
        ]
        asc_objs = {}
        for name, district, addr in ascs_data:
            obj, _ = ASCCentre.objects.get_or_create(
                name=name,
                defaults={"district": district, "address": addr}
            )
            asc_objs[name] = obj
        self.stdout.write(f"  [OK] 5 Northern ASC Centres configured.")

        # 3. Fertilizer Products (Urea, TSP, MOP 50kg)
        p_urea, _ = FertilizerProduct.objects.get_or_create(
            name="Urea",
            defaults={"bag_weight_kg": Decimal("50.00")}
        )
        p_tsp, _ = FertilizerProduct.objects.get_or_create(
            name="TSP",
            defaults={"bag_weight_kg": Decimal("50.00")}
        )
        p_mop, _ = FertilizerProduct.objects.get_or_create(
            name="MOP",
            defaults={"bag_weight_kg": Decimal("50.00")}
        )
        self.stdout.write("  [OK] 3 Fertilizer Products configured.")

        # 4. Cultivation Seasons (Active Maha 2026/2027 + Closed Yala 2026)
        today = timezone.localdate()
        s_maha, _ = Season.objects.get_or_create(
            name="Maha 2026/2027",
            defaults={
                "start_date": datetime.date(2026, 9, 1),
                "end_date": datetime.date(2027, 3, 31),
                "status": Season.StstusChoices.ACTIVE
            }
        )
        s_yala, _ = Season.objects.get_or_create(
            name="Yala 2026",
            defaults={
                "start_date": datetime.date(2026, 4, 1),
                "end_date": datetime.date(2026, 8, 31),
                "status": Season.StstusChoices.CLOSED
            }
        )
        self.stdout.write("  [OK] Cultivation Seasons configured (Active: Maha 2026/2027).")

        # 5. Fertilizer Batches (Fresh, Near-Expiry <60d, Expired)
        b_fresh_urea, _ = FertilizerBatch.objects.get_or_create(
            batch_number="UREA-2026-B01",
            defaults={
                "product": p_urea,
                "warehouse": wh_vavuniya,
                "expiry_date": today + datetime.timedelta(days=240)  # Healthy: ~8 months
            }
        )
        b_near_urea, _ = FertilizerBatch.objects.get_or_create(
            batch_number="UREA-2026-NE01",
            defaults={
                "product": p_urea,
                "warehouse": wh_vavuniya,
                "expiry_date": today + datetime.timedelta(days=35)  # Near-expiry: 35 days (FEFO Priority!)
            }
        )
        b_exp_urea, _ = FertilizerBatch.objects.get_or_create(
            batch_number="UREA-2025-EXP01",
            defaults={
                "product": p_urea,
                "warehouse": wh_vavuniya,
                "expiry_date": today - datetime.timedelta(days=15)  # Expired 15 days ago
            }
        )
        b_fresh_tsp, _ = FertilizerBatch.objects.get_or_create(
            batch_number="TSP-2026-B01",
            defaults={
                "product": p_tsp,
                "warehouse": wh_colombo,
                "expiry_date": today + datetime.timedelta(days=300)
            }
        )
        b_near_mop, _ = FertilizerBatch.objects.get_or_create(
            batch_number="MOP-2026-NE01",
            defaults={
                "product": p_mop,
                "warehouse": wh_colombo,
                "expiry_date": today + datetime.timedelta(days=45)  # Near-expiry: 45 days
            }
        )
        self.stdout.write("  [OK] Diverse Fertilizer Batches configured (Fresh, Near-Expiry FEFO, Expired).")

        # 6. Demo User Accounts per Role
        default_pwd = "Password123!"

        # Admin
        u_admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@agrian.gov.lk",
                "role": "ADMIN",
                "is_staff": True,
                "is_superuser": True,
                "is_account_active": True,
                "failed_login_attempts": 0,
            }
        )
        if created:
            u_admin.set_password(default_pwd)
            u_admin.save()

        # Warehouse Officer
        u_wh, created = User.objects.get_or_create(
            username="wh_officer",
            defaults={
                "email": "warehouse.officer@agrian.gov.lk",
                "role": "WAREHOUSE_OFFICER",
                "is_account_active": True,
                "failed_login_attempts": 0,
            }
        )
        if created:
            u_wh.set_password(default_pwd)
            u_wh.save()

        # ASC Officer (Vavuniya South)
        u_asc, created = User.objects.get_or_create(
            username="asc_officer",
            defaults={
                "email": "asc.officer@agrian.gov.lk",
                "role": "ASC_OFFICER",
                "asc_centre": asc_objs["Vavuniya South ASC"],
                "is_asc_head": False,
                "is_account_active": True,
                "failed_login_attempts": 0,
            }
        )
        if created:
            u_asc.set_password(default_pwd)
            u_asc.save()

        # ASC Head (Vavuniya South)
        u_head, created = User.objects.get_or_create(
            username="asc_head",
            defaults={
                "email": "asc.head@agrian.gov.lk",
                "role": "ASC_OFFICER",
                "asc_centre": asc_objs["Vavuniya South ASC"],
                "is_asc_head": True,
                "is_account_active": True,
                "failed_login_attempts": 0,
            }
        )
        if created:
            u_head.set_password(default_pwd)
            u_head.save()

        # Auditor
        u_auditor, created = User.objects.get_or_create(
            username="auditor",
            defaults={
                "email": "auditor@agrian.gov.lk",
                "role": "AUDITOR",
                "is_account_active": True,
                "failed_login_attempts": 0,
            }
        )
        if created:
            u_auditor.set_password(default_pwd)
            u_auditor.save()

        # Farmer Demo User (farmer1)
        u_farmer, created = User.objects.get_or_create(
            username="farmer1",
            defaults={
                "email": "farmer1@agrian.gov.lk",
                "role": "FARMER",
                "is_account_active": True,
                "failed_login_attempts": 0,
            }
        )
        if created:
            u_farmer.set_password(default_pwd)
            u_farmer.save()

        self.stdout.write("  [OK] Demo role accounts configured (Password: Password123!).")

        # 7. ASC Stocks Setup (FEFO priority, Low stock, Expired stock)
        asc_vs = asc_objs["Vavuniya South ASC"]
        asc_ched = asc_objs["Cheddikulam ASC"]
        asc_oman = asc_objs["Omanthai ASC"]

        # Vavuniya South: Near-expiry (12 bags), Fresh (40 bags), Expired (8 bags for write-off test)
        st_vs_near, _ = ASCStock.objects.get_or_create(
            asc_centre=asc_vs,
            batch=b_near_urea,
            defaults={"bags_on_hand": 12}
        )
        st_vs_fresh, _ = ASCStock.objects.get_or_create(
            asc_centre=asc_vs,
            batch=b_fresh_urea,
            defaults={"bags_on_hand": 40}
        )
        st_vs_exp, _ = ASCStock.objects.get_or_create(
            asc_centre=asc_vs,
            batch=b_exp_urea,
            defaults={"bags_on_hand": 8}
        )
        # Cheddikulam: Low stock (4 bags < 10 threshold)
        st_ched_low, _ = ASCStock.objects.get_or_create(
            asc_centre=asc_ched,
            batch=b_fresh_urea,
            defaults={"bags_on_hand": 4}
        )
        # Omanthai: TSP (25 bags)
        st_oman_tsp, _ = ASCStock.objects.get_or_create(
            asc_centre=asc_oman,
            batch=b_fresh_tsp,
            defaults={"bags_on_hand": 25}
        )
        self.stdout.write("  [OK] ASC Stock balances initialized with FEFO alerts and low-stock conditions.")

        # 8. Dispatches in Various States (Dispatched, Received, Discrepancy)
        # Dispatch 1: Received Good
        d_received, _ = StockDispatch.objects.get_or_create(
            dispatch_reference="DSP-2026-VAV01",
            defaults={
                "warehouse": wh_vavuniya,
                "asc_centre": asc_vs,
                "status": StockDispatch.StatusChoices.RECEIVED,
                "created_by": u_wh
            }
        )
        DispatchItem.objects.get_or_create(
            dispatch=d_received,
            batch=b_fresh_urea,
            defaults={"dispatched_bags": 50, "received_bags": 50, "damaged_bags": 0}
        )

        # Dispatch 2: Received with Discrepancy
        d_disc, _ = StockDispatch.objects.get_or_create(
            dispatch_reference="DSP-2026-OMN01",
            defaults={
                "warehouse": wh_vavuniya,
                "asc_centre": asc_oman,
                "status": StockDispatch.StatusChoices.RECEIVED_WITH_DISCREPANCY,
                "created_by": u_wh
            }
        )
        DispatchItem.objects.get_or_create(
            dispatch=d_disc,
            batch=b_fresh_tsp,
            defaults={"dispatched_bags": 30, "received_bags": 27, "damaged_bags": 2}
        )
        Discrepancy.objects.get_or_create(
            dispatch=d_disc,
            defaults={
                "damaged_bags": 2,
                "missing_bags": 1,
                "reason": "Rainwater seepage through truck tarpaulin damaged 2 bags on A9; 1 bag short during count.",
                "recorded_by": u_asc
            }
        )

        # Dispatch 3: In Transit (DISPATCHED)
        d_transit, _ = StockDispatch.objects.get_or_create(
            dispatch_reference="DSP-2026-CHD01",
            defaults={
                "warehouse": wh_colombo,
                "asc_centre": asc_ched,
                "status": StockDispatch.StatusChoices.DISPATCHED,
                "created_by": u_wh
            }
        )
        DispatchItem.objects.get_or_create(
            dispatch=d_transit,
            batch=b_near_mop,
            defaults={"dispatched_bags": 20, "received_bags": 0, "damaged_bags": 0}
        )
        self.stdout.write("  [OK] Realistic Dispatches seeded (Received, Discrepancy, In-Transit).")

        # 9. Realistic Farmers Dataset (~30 Farmers across Vavuniya)
        farmers_raw = [
            ("K. Selvaratnam", "197812345678", "0771234501", "Pandarikkulam, Vavuniya South", asc_vs, u_farmer),
            ("S. Tharmalingam", "198223456789", "0771234502", "Kurumankadu, Vavuniya South", asc_vs, None),
            ("M. Sivakumar", "196534567890", "0771234503", "Rambaikulam, Vavuniya South", asc_vs, None),
            ("P. Rasiah", "195445678901", "", "Vepankulam, Vavuniya South", asc_vs, None),  # No phone (Assisted demo!)
            ("K. Gunaratne", "197656789012", "0771234505", "Mahakachchakodiya, Vavuniya", asc_vs, None),
            ("N. Bandara", "198567890123", "0771234506", "Iratperiyakulam, Vavuniya", asc_vs, None),
            ("S. Wickramasinghe", "197278901234", "0771234507", "Madukanda, Vavuniya South", asc_vs, None),
            ("A. Mohamed", "198889012345", "0771234508", "Pattaniyoor, Vavuniya", asc_vs, None),
            ("R. Jeyaraj", "196990123456", "", "Sasthrikoolankulam, Vavuniya", asc_vs, None),  # No phone (Assisted demo!)
            ("T. Kandasamy", "198001234567", "0771234510", "Asikulam, Vavuniya", asc_vs, None),

            # Cheddikulam Farmers
            ("V. Navaratnam", "197511223344", "0772233401", "Cheddikulam Town, Vavuniya", asc_ched, None),
            ("M. Perera", "198322334455", "0772233402", "Periyapuliyankulam, Cheddikulam", asc_ched, None),
            ("S. Krishnan", "196833445566", "", "Neriyakulam, Cheddikulam", asc_ched, None),  # No phone
            ("A. Karunakaran", "199044556677", "0772233404", "Menik Farm, Cheddikulam", asc_ched, None),
            ("K. Balachandran", "198155667788", "0772233405", "Andiyapuliyankulam, Cheddikulam", asc_ched, None),

            # Nedunkeni Farmers
            ("S. Murugesu", "197466778899", "0773344501", "Nedunkeni Town, Vavuniya North", asc_objs["Nedunkeni ASC"], None),
            ("T. Arumugam", "196777889900", "0773344502", "Koolankulam, Nedunkeni", asc_objs["Nedunkeni ASC"], None),
            ("P. Velupillai", "195888990011", "", "Maruthodai, Nedunkeni", asc_objs["Nedunkeni ASC"], None),  # No phone
            ("N. Jayasundara", "198699001122", "0773344504", "Mamaduwa, Nedunkeni", asc_objs["Nedunkeni ASC"], None),
            ("C. Rathnayake", "197900112233", "0773344505", "Kanchuramoddai, Nedunkeni", asc_objs["Nedunkeni ASC"], None),

            # Omanthai Farmers
            ("K. Yogarajah", "197212349988", "0774455601", "Omanthai Junction, Vavuniya", asc_oman, None),
            ("R. Sivarajah", "198423458877", "0774455602", "Palamottai, Omanthai", asc_oman, None),
            ("S. Sinnathamby", "196334567766", "", "Maravanpulavu, Omanthai", asc_oman, None),  # No phone
            ("D. Dissanayake", "199145676655", "0774455604", "Arasankulam, Omanthai", asc_oman, None),
            ("M. Fernando", "198756785544", "0774455605", "Navvi, Omanthai", asc_oman, None),

            # Puliyankulam Farmers
            ("T. Subramaniam", "197067894433", "0775566701", "Puliyankulam Centre", asc_objs["Puliyankulam ASC"], None),
            ("K. Theivendran", "198978903322", "0775566702", "Kanagarayankulam, Puliyankulam", asc_objs["Puliyankulam ASC"], None),
            ("S. Mahendran", "197789012211", "0775566703", "Aiyanankulam, Puliyankulam", asc_objs["Puliyankulam ASC"], None),
            ("H. Senaratne", "198290121100", "0775566704", "Koolankulam Road, Puliyankulam", asc_objs["Puliyankulam ASC"], None),
            ("B. Kulatunga", "199301230099", "0775566705", "Puthur, Puliyankulam", asc_objs["Puliyankulam ASC"], None),
        ]

        farmer_objs = []
        for name, nic, phone, addr, asc, u_acc in farmers_raw:
            f_obj = Farmer.objects.filter(nic_number=nic).first()
            if not f_obj and u_acc:
                f_obj = Farmer.objects.filter(user=u_acc).first()

            if not f_obj:
                assigned_user = u_acc if (u_acc and not Farmer.objects.filter(user=u_acc).exists()) else None
                f_obj = Farmer.objects.create(
                    nic_number=nic,
                    full_name=name,
                    mobile_number=phone or "0770000000",
                    arpa_division=addr,
                    user=assigned_user
                )
            else:
                f_obj.full_name = name
                if phone:
                    f_obj.mobile_number = phone
                f_obj.arpa_division = addr
                if u_acc and not Farmer.objects.filter(user=u_acc).exclude(id=f_obj.id).exists():
                    f_obj.user = u_acc
                f_obj.save()

            farmer_objs.append(f_obj)

            # Assign Entitlements for Maha 2026/2027
            FarmerEntitlement.objects.get_or_create(
                farmer=f_obj,
                season=s_maha,
                product=p_urea,
                defaults={"approved_kg": Decimal("150.00"), "remaining_kg": Decimal("150.00")}
            )
            FarmerEntitlement.objects.get_or_create(
                farmer=f_obj,
                season=s_maha,
                product=p_tsp,
                defaults={"approved_kg": Decimal("50.00"), "remaining_kg": Decimal("50.00")}
            )
            FarmerEntitlement.objects.get_or_create(
                farmer=f_obj,
                season=s_maha,
                product=p_mop,
                defaults={"approved_kg": Decimal("50.00"), "remaining_kg": Decimal("50.00")}
            )

        self.stdout.write(f"  [OK] {len(farmer_objs)} Sri Lankan farmers and Maha 2026/2027 entitlements seeded.")

        # 10. Pre-seed a few sample distributions for demo demonstration
        first_farmer = farmer_objs[0]  # K. Selvaratnam
        ent_urea = FarmerEntitlement.objects.get(farmer=first_farmer, season=s_maha, product=p_urea)
        ent_urea.remaining_kg = Decimal("100.00")
        ent_urea.save()

        dist1, _ = FertilizerDistribution.objects.get_or_create(
            receipt_number="REC-DEMO0001",
            defaults={
                "farmer": first_farmer,
                "asc_centre": asc_vs,
                "batch": b_near_urea,
                "season": s_maha,
                "issued_by": u_asc,
                "issue_method": FertilizerDistribution.IssueMethodChoices.QR,
                "quantity_kg": Decimal("50.00")
            }
        )
        StockMovement.objects.get_or_create(
            notes="Issued to Farmer 197812345678 via QR Code (Receipt: REC-DEMO0001)",
            defaults={
                "stock": st_vs_near,
                "movement_type": StockMovement.MovementTypeChoices.OUTBOUND,
                "quantity_kg": Decimal("50.00"),
                "created_by": u_asc
            }
        )

        # Pre-seed a pending assisted request for demonstration
        no_phone_farmer = farmer_objs[3]  # P. Rasiah (no phone)
        assisted_req, _ = AssistedIssueApproval.objects.get_or_create(
            farmer=no_phone_farmer,
            asc_centre=asc_vs,
            season=s_maha,
            requested_by=u_asc,
            defaults={
                "reason": AssistedIssueApproval.ReasonChoices.NO_PHONE,
                "reason_note": "Elderly farmer does not own a mobile phone. Identity verified via original National Identity Card.",
                "status": AssistedIssueApproval.StatusChoices.PENDING,
                "expires_at": timezone.now() + datetime.timedelta(minutes=25)
            }
        )

        AuditLog.objects.create(
            user=u_admin,
            action="SYSTEM_DEMO_DATA_SEEDED",
            details="Demo dataset initialized successfully via seed_demo_data command."
        )

        self.stdout.write(self.style.SUCCESS("\n======================================================="))
        self.stdout.write(self.style.SUCCESS("FertiTracker Demo Dataset Successfully Initialized!"))
        self.stdout.write(self.style.SUCCESS("======================================================="))
        self.stdout.write("Credentials (Password for all accounts is: Password123!):")
        self.stdout.write("  - Administrator:     admin")
        self.stdout.write("  - Warehouse Officer: wh_officer")
        self.stdout.write("  - ASC Counter:       asc_officer (Vavuniya South)")
        self.stdout.write("  - ASC Head:          asc_head    (Vavuniya South, Approver)")
        self.stdout.write("  - Auditor:           auditor")
        self.stdout.write("  - Farmer Account:    farmer1     (K. Selvaratnam)")
        self.stdout.write(self.style.SUCCESS("=======================================================\n"))
